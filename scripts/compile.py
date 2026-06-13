"""Compile daily logs and raw sources into wiki knowledge articles.

Usage:
    uv run python compile.py                  # compile all unprocessed files
    uv run python compile.py --all            # recompile everything
    uv run python compile.py --file daily/X.md
    uv run python compile.py --dry-run        # show what would be compiled
    uv run python compile.py --max-files=250  # compile at most 250 files, then stop (for large backlogs; default: 100)
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "compile"

import argparse
import asyncio
import fcntl
import io
import json
import logging
import re
import sys
import time
from pathlib import Path

from core.paths import INDEX_FILE, KNOWLEDGE_DIR, LOGS_DIR, LOG_FILE, ROOT_DIR, STATE_DIR, STATE_FILE
from core.utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    now_iso,
    save_state,
    today_iso,
)
from core.sdk_helpers import FailureClass, is_fatal

# ── Logging ──────────────────────────────────────────────────────────
# Generic console formatting + file handlers come from `core.console`.
# compile-specific colorization (per-file header, dispatch, curiosity)
# lives in `_CompileFormatter` below as a thin subclass.

from core.console import (  # noqa: E402
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_RESET,
    C_YELLOW,
    ConsoleFormatter,
    setup_console_logging,
)


class _CompileFormatter(ConsoleFormatter):
    """compile.py-specific layers on top of the generic formatter.

    Patterns owned here (subclass hook overrides them before the generic
    ✓/✗/cost/elapsed/tokens pass runs):

      - per-file header `[N/M] [badge] path`  → bold cyan, ▶ marker, badge yellow
      - dispatch line   `  type=X → prompt @ model`  → dim
      - curiosity line  `  Curiosity*`  → dim cyan + `?` prefix
                                          (info, not action; magenta read as
                                          error in dark terminals; the `?`
                                          glyph signals "inquiry")
    """

    _HEADER_RE = re.compile(r"^\[(\d+/\d+)\]\s+\[([^\]]+)\]\s+(\S+)$")
    _DISPATCH_RE = re.compile(r"^\s+type=[\w-]+\s+→")
    _CURIOSITY_RE = re.compile(r"^\s+Curiosity[: ]")

    def _format_message_extras(self, msg: str) -> str | None:
        if (mh := self._HEADER_RE.match(msg.strip())):
            pos, badge, path = mh.group(1), mh.group(2), mh.group(3)
            return (
                f"{C_BOLD}{C_CYAN}▶ [{pos}] "
                f"{C_YELLOW}[{badge}]{C_CYAN} {path}{C_RESET}"
            )
        if self._DISPATCH_RE.match(msg):
            return f"{C_DIM}{msg}{C_RESET}"
        if self._CURIOSITY_RE.match(msg):
            marked = re.sub(r"^(\s+)Curiosity", r"\1? Curiosity", msg, count=1)
            return f"{C_DIM}{C_CYAN}{marked}{C_RESET}"
        return None


LOGS_DIR.mkdir(parents=True, exist_ok=True)
log = setup_console_logging(
    "compile",
    formatter=_CompileFormatter(),
    log_file=LOGS_DIR / "compile.log",
    error_file=LOGS_DIR / "compile-errors.log",
)

from core.config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402
from core import ollama_client  # noqa: E402
from core.piggybacks import run_due_piggybacks  # noqa: E402

from compile_stages.post_passes import run_post_passes  # noqa: E402
from compile_stages.types import CompileOutcome  # noqa: E402
from compile_stages.route import (  # noqa: E402
    SUBSTRATE_PROMPTS,
    _DEFAULT_DISPATCH,
    _frontmatter_compile_role,
    _frontmatter_field,
    _frontmatter_type,
    _health_rollup_body_is_stub,
    _parse_frontmatter,
    _substrate_key,
)


# ── File selection ───────────────────────────────────────────────────

def select_files(args: argparse.Namespace) -> list[Path]:
    """Determine which files to compile based on CLI args and state."""
    state = load_state()
    ingested = state.get("ingested", {})

    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = ROOT_DIR / target
        if not target.exists():
            log.error("File not found: %s", target)
            sys.exit(1)
        return [target]

    candidates = list_raw_files()

    if args.all:
        return candidates

    # Filter to files that have changed since last compilation
    changed = []
    for f in candidates:
        current_hash = file_hash(f)
        rel = str(f.relative_to(ROOT_DIR))
        if ingested.get(rel) != current_hash:
            changed.append(f)

    return changed


# ── Compilation ──────────────────────────────────────────────────────


def _category_badge(rel_path: str) -> str:
    """Short tag for the source category — first path segment after raw/, or 'daily'."""
    if rel_path.startswith("daily/"):
        return "daily"
    if rel_path.startswith("raw/"):
        parts = rel_path.split("/")
        if len(parts) >= 3 and parts[1] == "notes":
            return parts[2]  # screenshots / email / browser / etc.
        if len(parts) >= 2:
            return parts[1]  # memories / articles / papers / etc.
    return "?"


async def compile_file(
    source: Path,
    dry_run: bool = False,
    prefix: str = "",
    *,
    force: bool = False,
) -> CompileOutcome:
    """Compile a single source file into wiki articles.

    Returns usage/cost info dict, or None on failure.

    ``force=True`` bypasses the substrate-type skip-list (used when the
    operator targets a single file via ``--file``; batch mode always
    honors the skip-list).
    """
    rel_path = str(source.relative_to(ROOT_DIR))
    badge = _category_badge(rel_path)
    log.info("%s[%s] %s", prefix, badge, rel_path)

    if dry_run:
        log.info("  [dry-run] Would compile %s", rel_path)
        return CompileOutcome(status="skipped", skip_reason="dry_run")

    source_content = source.read_text(encoding="utf-8")

    # Routing decision (compile_stages.route.decide_route) — pure: compile_role
    # inference, substrate skip-list, dispatch precedence, classify. compile_file
    # only EXECUTES the route below. The memory pre-pass (writes a Timeline
    # section) is I/O, so it stays here in the Compile arm, not in decide_route.
    from compile_stages.route import (
        Compile,
        HealthStub,
        IndexOnly,
        Skip,
        decide_route,
    )

    route = decide_route(source, source_content, force=force)

    if isinstance(route, Skip):
        if route.reason == "empty":
            log.warning("  Skipping empty file: %s", rel_path)
        elif route.reason == "compile_role_final_only":
            log.warning(
                "  skipping: compile_role=final-only (hand-curated, engine-skip)",
            )
        elif route.reason.startswith("substrate_type_excluded_"):
            log.info(
                "  skipping: type=%s is in compile_skip_substrate_types "
                "(use `wiki compile --file <path>` to force)",
                route.reason[len("substrate_type_excluded_"):],
            )
        # Record the ingested-hash on deterministic skips (empty / final-only /
        # substrate-excluded), mirroring the IndexOnly + HealthStub routes. The
        # route decision is a stable "never compile this content as-is" verdict,
        # so without this the file is re-selected as a candidate on EVERY run
        # forever — `select_files` re-lists any file whose hash isn't in
        # `state["ingested"]`. That polluted "Files to compile: N" with immortal
        # email-delta + final-only sources (34 + 3 on lxw, 2026-06-02). If the
        # body later changes, the hash mismatch correctly re-evaluates it.
        return CompileOutcome(
            status="skipped", skip_reason=route.reason, ingest_hash=True,
        )

    if isinstance(route, IndexOnly):
        return _run_index_only(source, rel_path, route)

    if isinstance(route, HealthStub):
        return _run_health_stub(source, rel_path)

    return await _run_compile_route(source, source_content, rel_path, route)


def _run_index_only(source: Path, rel_path: str, route) -> dict:
    """Execute the source-and-final IndexOnly route: append a knowledge/index.md
    entry by pathname (no SDK distill, no separate concept article), then mark the
    file ingested so re-runs no-op and check_orphan_sources doesn't flag it."""
    from core.utils import build_index_entry
    log.info(
        "  source-and-final: indexing only (no distill) — %d wikilinks discovered",
        len(route.wikilinks),
    )
    new_entry = build_index_entry(
        rel_path, route.title, "(source-and-final)", today_iso(),
    )
    if INDEX_FILE.exists():
        existing = INDEX_FILE.read_text(encoding="utf-8")
        link_marker = f"[[{rel_path.replace('.md', '')}]]"
        if link_marker not in existing:
            with INDEX_FILE.open("a", encoding="utf-8") as f:
                f.write(f"\n{new_entry}")
            log.info("  added to knowledge/index.md")
        else:
            log.info("  already in knowledge/index.md (no-op)")
    else:
        log.warning(
            "  knowledge/index.md missing — cannot index source-and-final file",
        )
    return CompileOutcome(
        status="skipped",
        skip_reason="compile_role_source_and_final_indexed",
        ingest_hash=True,
    )


def _run_health_stub(source: Path, rel_path: str) -> dict:
    """Execute the HealthStub route: record the metric-only stub deterministically
    (mark ingested), no agent, no knowledge writes, $0. 2026-05-22 root-cause."""
    log.info(
        "  health-rollup stub-body — deterministic record "
        "(no agent, no knowledge writes, $0)"
    )
    return CompileOutcome(
        status="skipped",
        skip_reason="health_rollup_stub_deterministic",
        ingest_hash=True,
    )


async def _run_compile_route(
    source: Path, source_content: str, rel_path: str, route
) -> dict | None:
    """Execute the Compile route: dispatch-decision log, memory pre-pass (I/O —
    bootstraps a Timeline section + enriches metadata), then the chunk/single
    compile_source call(s). Returns the legacy usage/skip/failure dict."""
    metadata = route.metadata
    classification = route.classification
    source_type = metadata.substrate_type

    # Dispatch decision log (only for explicit SUBSTRATE_PROMPTS matches — skip
    # the noise of "type=X → default" for the safe-by-default fallback).
    if _substrate_key(source_content, rel_path) in SUBSTRATE_PROMPTS:
        short_model = ""
        if metadata.model_id:
            m = re.match(r"claude-(haiku|sonnet|opus)-(\d+-\d+)", metadata.model_id)
            short_model = (
                f" @ {m.group(1)}-{m.group(2)}" if m else f" @ {metadata.model_id}"
            )
        log.info("  type=%s → %s%s", source_type, metadata.substrate_prompt, short_model)

    # Memory-substrate pre-pass: resolve target project page + bootstrap the
    # `## Timeline` section deterministically so the SDK call is mechanical.
    # I/O (writes Timeline) — stays here, not in pure decide_route. Enriches the
    # route's metadata via dataclasses.replace.
    if source_type in ("memory-sync", "memory-seed"):
        import dataclasses
        from compile_stages.memory import (
            ensure_timeline_section,
            resolve_project_slug,
        )
        fm = _parse_frontmatter(source_content)
        project_slug = resolve_project_slug(source, fm, ROOT_DIR)
        if project_slug is None:
            log.info(
                "  memory pre-pass: type=%s — no matching knowledge/projects/<slug>.md "
                "(filename stem, frontmatter project:, tags all unresolved). "
                "Falling through to free-distill mode — agent will produce "
                "concept stubs from the memory body.",
                source_type,
            )
        else:
            project_page = KNOWLEDGE_DIR / "projects" / f"{project_slug}.md"
            ensure_timeline_section(project_page)
            project_page_rel = str(project_page.relative_to(ROOT_DIR))
            log.info(
                "  memory pre-pass: project=%s page=%s (Timeline bootstrapped if absent)",
                project_slug, project_page_rel,
            )
            metadata = dataclasses.replace(
                metadata,
                project_slug=project_slug,
                project_page_rel=project_page_rel,
            )

    from compile_stages.compile import compile_source

    if classification.kind == "aggregated-memory":
        log.info(
            "  classified as aggregated-memory -> splitting into %d "
            "per-section compile calls (raw file untouched)",
            len(classification.chunks),
        )
        chunk_results = []
        any_ok = False
        # Circuit-breaker: aborts after N consecutive chunk failures
        # (skipped OR failed) to stop runaway $-burn on a substrate-prompt
        # mismatch. Per-file cost guard fires per-chunk, not cumulatively,
        # so a 46-chunk file with broken prompt could burn $16+ without
        # this. Counter resets on each ok chunk.
        abort_after = CONFIG.limits.compile_aggregated_max_consecutive_failures
        consecutive_failures = 0
        aborted_at: int | None = None
        for i, chunk in enumerate(classification.chunks, 1):
            if abort_after and consecutive_failures >= abort_after:
                log.warning(
                    "  aggregated-memory: aborting chunk loop after %d "
                    "consecutive failures (%d/%d chunks processed). "
                    "Substrate-prompt mismatch likely; revise "
                    "`prompts/compile_memories.md` or add `%s` to "
                    "`compile_skip_substrate_types`. Already-ok chunks "
                    "preserved.",
                    consecutive_failures, i - 1, len(classification.chunks),
                    source_type,
                )
                aborted_at = i - 1
                break
            log.info("  chunk %d/%d (%d chars)", i, len(classification.chunks), len(chunk))
            chunk_result = await compile_source(chunk, metadata)
            chunk_results.append(chunk_result)
            if chunk_result.status == "ok":
                any_ok = True
                consecutive_failures = 0
            else:
                consecutive_failures += 1
        total_in = sum(r.input_tokens or 0 for r in chunk_results)
        total_out = sum(r.output_tokens or 0 for r in chunk_results)
        total_cost = sum(r.cost_usd or 0 for r in chunk_results)
        ok_count = sum(1 for r in chunk_results if r.status == "ok")
        skip_count = sum(1 for r in chunk_results if r.status == "skipped")
        fail_count = sum(1 for r in chunk_results if r.status == "failed")
        log.info(
            "  aggregated-memory result: %d ok / %d skipped / %d failed "
            "(total in:%d out:%d $%.4f)%s",
            ok_count, skip_count, fail_count, total_in, total_out, total_cost,
            f" — ABORTED at chunk {aborted_at}/{len(classification.chunks)}"
            if aborted_at is not None else "",
        )
        if not any_ok:
            return CompileOutcome(
                status="skipped",
                skip_reason=(
                    "aggregated_memory_circuit_breaker"
                    if aborted_at is not None
                    else "aggregated_memory_all_chunks_failed"
                ),
            )
        return CompileOutcome(
            status="compiled",
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
            article=(
                f"aggregated-memory: {ok_count}/{len(classification.chunks)} "
                f"chunks compiled"
                + (f" (aborted at {aborted_at})" if aborted_at is not None else "")
            ),
            ingest_hash=True,
        )

    result = await compile_source(source_content, metadata)

    if result.status == "skipped":
        # Map compile_source's skip_reason to the legacy skip tags; they differ
        # only for the long-context kind=unknown case.
        legacy_reason = {
            "long_context_kind_unknown": "kind_unknown_on_long_context",
        }.get(result.skip_reason or "", result.skip_reason or "unknown")
        return CompileOutcome(status="skipped", skip_reason=legacy_reason)

    if result.status == "failed":
        return CompileOutcome(
            status="failed",
            failure_kind=result.failure_kind or "unknown",
            failure_detail=result.failure_detail or "(see logs)",
        )

    return CompileOutcome(
        status="compiled",
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        article=result.article or "",
        ingest_hash=True,
    )


# ── Process-level mutex ──────────────────────────────────────────────

_COMPILE_LOCK_FILE = STATE_DIR / "compile.lock"


def _acquire_exclusive_lock(lock_path: Path) -> io.IOBase | None:
    """Try to acquire an exclusive non-blocking flock on ``lock_path``.

    Returns the open file handle on success — caller MUST keep the
    reference alive for the duration of the critical section. The kernel
    releases the flock automatically on process exit (or on explicit
    ``handle.close()``), so no manual unlock is needed.

    Returns ``None`` if another process already holds the lock.

    Background: 2026-05-15 incident — parallel SessionEnd hooks each
    spawned ``compile.py --file daily/<X>.md`` for the same daily file,
    producing 3-4 concurrent bundled-CLI subprocesses that competed for
    the Claude subscription quota and crashed mid-stream with
    ``kind=unknown``/empty stderr. A single global compile-lock prevents
    the storm.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return None
    return fd


# ── Main ─────────────────────────────────────────────────────────────

def _spawn_maintenance() -> None:
    """Drain due piggybacks at the end of a real compile.

    The operator's loop is `wiki update && wiki compile`; the piggyback trigger
    used to live only in `flush.py` behind the `compile_after_hour` evening
    gate, so for a daytime-compile-only workflow none of dream-cycle / lint /
    curiosity-drain / daily-digest ever fired and their queues piled up. Here we
    spawn whatever is due (cooldown-gated, hour-gate bypassed), detached and
    non-blocking. Never let a spawn failure abort the compile that triggered it.
    """
    if not CONFIG.scheduling.piggybacks_on_compile:
        log.info("  maintenance: skipped (piggybacks_on_compile=false)")
        return
    try:
        spawned = run_due_piggybacks(ignore_hour_gate=True, log=log)
        # Always log — a silent path made it impossible to tell "ran, nothing
        # due" from "never ran" when verifying the compile→maintenance trigger.
        if spawned:
            log.info(
                "  maintenance: spawned %d due piggyback(s): %s",
                len(spawned), ", ".join(spawned),
            )
        else:
            log.info("  maintenance: 0 due — queues current")
    except Exception:  # noqa: BLE001 — maintenance must never break compile
        log.warning("  maintenance: piggyback spawn failed (continuing)", exc_info=True)


# Skip reasons whose branch mutates state["ingested"] on DISK from inside
# compile_file (source-and-final indexing; the deterministic health-rollup
# stub path). After such a skip the main loop's in-memory `state` is stale, so
# it MUST reload before its per-file/final save_state — otherwise that save
# clobbers the on-disk mark and the file is re-selected every run. Any future
# skip branch that writes state from inside compile_file must be added here.
async def main() -> None:
    parser = argparse.ArgumentParser(description="Compile sources into wiki articles")
    parser.add_argument("--all", action="store_true", help="Recompile all files")
    parser.add_argument("--file", type=str, help="Compile a specific file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be compiled"
    )
    parser.add_argument(
        "--max-files", type=int, default=CONFIG.limits.compile_max_files,
        help="Stop after N files (to stay under the 5h rate-limit window). 0 = unlimited.",
    )
    parser.add_argument(
        "--max-consecutive-failures", type=int,
        default=CONFIG.limits.compile_max_consecutive_failures,
        help="Abort run when this many files fail back-to-back (rate-limit signal).",
    )
    args = parser.parse_args()

    # Global mutex — only one compile process at a time. Concurrent spawns
    # from parallel SessionEnd hooks (or operator + hook) used to converge
    # on the same daily-file and crash the bundled CLI mid-stream under
    # subscription-quota contention. The lock is released on process exit.
    _compile_lock = _acquire_exclusive_lock(_COMPILE_LOCK_FILE)
    if _compile_lock is None:
        log.info(
            "Another compile process is already running (lock %s held) — exiting cleanly.",
            _COMPILE_LOCK_FILE,
        )
        return

    # Pre-compile sweep: move <vault>/Clippings/*.md into raw/articles/
    # so Obsidian Web Clipper output is visible to the source-glob below.
    # Cheap no-op if Clippings/ is empty or absent. Disable via
    # CONFIG.features.clippings_sweep = false if the Web Clipper extension
    # is reconfigured to drop directly into raw/articles/.
    if CONFIG.features.clippings_sweep:
        try:
            import clippings_sweep
            n_swept = clippings_sweep.sweep()
            if n_swept > 0:
                log.info("Pre-compile: swept %d file(s) from Clippings/ into raw/articles/", n_swept)
        except Exception as e:  # noqa: BLE001 — never let sweep failures abort compile
            log.warning("Pre-compile clippings sweep failed (continuing): %s", e)

    files = select_files(args)
    if not files:
        log.info("Nothing to compile — all files up to date.")
        # A no-op compile still keeps maintenance current — dream/lint/etc.
        # backlogs are independent of whether new sources landed this run.
        if not args.dry_run:
            _spawn_maintenance()
        return

    log.info("Files to compile: %d", len(files))
    for f in files:
        log.info("  %s", f.relative_to(ROOT_DIR))

    # `--file` is an explicit operator target; respect their intent and
    # bypass the substrate-type skip-list (which is for unattended batch
    # runs). Batch mode always honors the skip-list.
    force_compile = bool(args.file)

    if args.dry_run:
        for f in files:
            await compile_file(f, dry_run=True, force=force_compile)
        return

    # Ensure knowledge directories exist
    for subdir in ["concepts", "connections", "qa", "people", "projects"]:
        (KNOWLEDGE_DIR / subdir).mkdir(parents=True, exist_ok=True)

    state = load_state()
    total_cost = state.get("total_cost", 0.0)
    cost_at_start = total_cost  # for history-event cost_delta
    compiled_count = 0
    failed_count = 0
    skipped_count = 0
    consecutive_failures = 0
    recent_failures: list[FailureClass] = []
    aborted = False
    abort_reason = ""
    run_input_tokens = 0
    run_output_tokens = 0
    run_started = time.time()

    cap = min(args.max_files, len(files)) if args.max_files else len(files)
    log.info("─── compiling %d of %d candidates (newest first) ───", cap, len(files))

    for idx, source in enumerate(files, 1):
        if args.max_files and compiled_count >= args.max_files:
            log.info(
                "Reached --max-files limit of %d. Stopping. (Rerun later to continue.)",
                args.max_files,
            )
            break

        # Denominator is the full candidate count, not `cap`: deterministic
        # skips (health-rollup stubs, substrate-skip-list) don't increment
        # compiled_count, so the --max-files break only fires after `cap` REAL
        # compiles while idx runs through every candidate. Using `cap` here
        # produced a nonsensical `[1516/100]` when a big skip-backlog drained.
        prefix = f"[{idx}/{len(files)}] "
        try:
            outcome = await compile_file(source, prefix=prefix, force=force_compile)
        except Exception as exc:  # noqa: BLE001 — one file's crash must not kill the whole batch
            # An unhandled exception in compile_file used to propagate out of
            # main(), aborting the entire run AND skipping the end-of-run
            # maintenance drain. Demote it to a per-file failure so the batch
            # continues; the consecutive-failure abort still catches a systemic
            # problem. (CancelledError is a BaseException and intentionally not
            # caught — it's a real task/process cancellation that must propagate.)
            log.exception("  ✗ unhandled exception compiling %s", source.relative_to(ROOT_DIR))
            outcome = CompileOutcome(
                status="failed", failure_kind="exception",
                failure_detail=str(exc) or repr(exc),
            )

        if outcome.status == "skipped":
            # Skipped (empty / dry-run / skip-list / source-and-final / health-stub /
            # compile_source pre-flight skip): neither success nor failure. Don't touch
            # the failure-streak counter. Persist the ingested-hash here iff the route
            # asked for it (source-and-final + health-stub) — main() is now the SINGLE
            # state-save site (replaces the old _STATE_MUTATING_SKIPS reload dance).
            skipped_count += 1
            if outcome.ingest_hash:
                rel = str(source.relative_to(ROOT_DIR))
                state.setdefault("ingested", {})[rel] = file_hash(source)
                save_state(state)
            continue

        if outcome.status == "failed":
            failed_count += 1
            consecutive_failures += 1
            failure = FailureClass(
                outcome.failure_kind or "unknown",
                outcome.failure_detail or "(see logs)",
            )
            recent_failures.append(failure)
            # Fail-fast on auth/model errors — they will repeat identically for
            # every remaining file. Operator must fix config first.
            if is_fatal(failure):
                log.error(
                    "Fatal failure (kind=%s): %s. Aborting before wasting "
                    "more attempts on the same misconfiguration.",
                    failure.kind, failure.detail,
                )
                aborted = True
                abort_reason = f"fatal/{failure.kind}"
                break
            if consecutive_failures >= args.max_consecutive_failures:
                window = recent_failures[-consecutive_failures:]
                kinds = [f.kind for f in window]
                if "rate_limit" in kinds:
                    log.error(
                        "%d consecutive failures incl. rate_limit signal — "
                        "Anthropic 5h Opus window likely. Rerun in 60-90 min.",
                        consecutive_failures,
                    )
                    abort_reason = "rate_limit"
                elif kinds and all(k == "cli_crash" for k in kinds):
                    log.error(
                        "%d consecutive bundled-CLI fast-crashes (kind=cli_crash). "
                        "This is NOT a rate-limit. See [CLI-STDERR] above. "
                        "Sanity-check: `claude --version` and `claude -p \"hi\"`.",
                        consecutive_failures,
                    )
                    abort_reason = "cli_crash"
                elif "network" in kinds:
                    log.error(
                        "%d consecutive failures incl. network errors — "
                        "transient connectivity issue. Retry shortly.",
                        consecutive_failures,
                    )
                    abort_reason = "network"
                else:
                    log.error(
                        "%d consecutive failures (kinds=%s). See *-errors.log "
                        "for captured stderr. Aborting.",
                        consecutive_failures, ",".join(kinds) or "unknown",
                    )
                    abort_reason = "mixed"
                aborted = True
                break
            continue

        # Success (status == "compiled") — reset failure streak
        consecutive_failures = 0
        compiled_count += 1
        total_cost += outcome.cost_usd
        run_input_tokens += outcome.input_tokens
        run_output_tokens += outcome.output_tokens

        # Post-pass producers (Producer-seam arc, .ytstack/backlog/producer-seam.md).
        # `run_post_passes` iterates every registered Producer serially, absorbing
        # per-producer raises into ProducerResult(status="failed"). Per-producer LLM
        # usage is recorded centrally by the token ledger (core/usage.py).
        from compile_stages.types import CompileResult
        _compile_result = CompileResult(
            status="ok",
            cost_usd=outcome.cost_usd,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            article=outcome.article,
        )
        await run_post_passes(source, _compile_result, state)

        # Single state-save site: mark file ingested + persist immediately. Per-file
        # save (not just end-of-loop) so rate-limit aborts / kills / crashes don't lose
        # work already done. Iron rule: "no gap between capture and persist".
        rel = str(source.relative_to(ROOT_DIR))
        state.setdefault("ingested", {})[rel] = file_hash(source)
        state["total_cost"] = round(total_cost, 4)
        state["last_compile"] = now_iso()
        save_state(state)

    # Final save (idempotent — captures total_cost / last_compile if loop had
    # zero successes and the per-file save above was never reached).
    state["total_cost"] = round(total_cost, 4)
    state["last_compile"] = now_iso()
    save_state(state)

    # Corpus-wide backlinks footer pass (M020). Runs after every compile so
    # newly-created articles or renamed targets propagate into incoming-link
    # footers across the corpus. Idempotent — unchanged corpus produces zero
    # writes. Gated by features.materialize_backlinks so an operator can flip
    # it off if the per-compile read-sweep ever becomes a load concern.
    if CONFIG.features.materialize_backlinks:
        from core.backlinks import run_backlinks_pass
        bl_stats = run_backlinks_pass(KNOWLEDGE_DIR)
        log.info(
            "  backlinks pass: %d articles seen · %d rewritten",
            bl_stats["articles_seen"], bl_stats["articles_written"],
        )

    # Relativize wikilinks corpus-wide so cross-article links resolve in
    # Obsidian from nested folders (a link in a markdown file is relative to
    # that file). Runs after backlinks so freshly-written footers are
    # normalized too. Idempotent — already-relative links produce zero writes.
    if CONFIG.features.relativize_wikilinks:
        from core.links import run_relativize_pass
        rl_stats = run_relativize_pass(KNOWLEDGE_DIR, ROOT_DIR)
        log.info(
            "  relativize pass: %d articles seen · %d rewritten · %d links",
            rl_stats["articles_seen"], rl_stats["articles_written"],
            rl_stats["links_rewritten"],
        )

    # Append-only history event so Dashboard P2 charts can render time series.
    if compiled_count > 0:
        from core.utils import append_history
        append_history(
            "compile",
            articles_total=len(list_wiki_articles()),
            compiled_this_run=compiled_count,
            failed_this_run=failed_count,
            cost_delta=round(total_cost - cost_at_start, 4),
            cost_total=state["total_cost"],
            tokens_this_run=run_input_tokens + run_output_tokens,
        )

    outcome = f"ABORTED ({abort_reason or 'unknown'})" if aborted else "complete"
    # `pending` = files the batch never reached (--max-files cutoff, abort, etc.).
    # Skipped files were processed-and-intentionally-dropped (skip-list, empty,
    # dry-run) and are NOT pending — surface them separately so the summary
    # doesn't read "0 done · 10 pending" after a clean run that only saw
    # skip-list hits.
    pending = len(files) - compiled_count - failed_count - skipped_count
    elapsed_min, elapsed_sec = divmod(int(time.time() - run_started), 60)
    # Use the SDK-reported per-file cost deltas (already summed into
    # total_cost in the per-file loop) rather than re-deriving from
    # token counts. The token formula assumed Opus pricing on raw input
    # tokens, but Haiku/Sonnet-routed substrates use different rates and
    # SDK reports cache-discounted token counts — both biases compounded
    # to a 50-80× under-report on Haiku-heavy runs.
    run_cost = round(total_cost - cost_at_start, 4)
    log.info("─── compilation %s ───", outcome)
    log.info(
        "  files:   %d done · %d failed · %d skipped · %d pending of %d candidates",
        compiled_count, failed_count, skipped_count, pending, len(files),
    )
    log.info(
        "  tokens:  in:%s · out:%s · this run",
        f"{run_input_tokens:,}", f"{run_output_tokens:,}",
    )
    log.info(
        "  cost:    $%.4f this run · $%.4f lifetime",
        run_cost, total_cost,
    )
    log.info("  time:    %dm %ds", elapsed_min, elapsed_sec)

    # Drain due maintenance (dream/lint/curiosity/digests) now that the corpus
    # reflects this run. Detached + cooldown-gated; the dry-run path returned
    # earlier so this only fires on real compiles. Skipped after an abort —
    # a consecutive-failure abort is a rate-limit signal, and piling cloud
    # piggybacks (dream-cycle) onto that window only deepens the hole.
    if not aborted:
        _spawn_maintenance()


if __name__ == "__main__":
    asyncio.run(main())
