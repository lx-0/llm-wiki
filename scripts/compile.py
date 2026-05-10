"""Compile daily logs and raw sources into wiki knowledge articles.

Usage:
    uv run python compile.py                  # compile all unprocessed files
    uv run python compile.py --all            # recompile everything
    uv run python compile.py --file daily/X.md
    uv run python compile.py --dry-run        # show what would be compiled
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "compile"

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx  # noqa: E402  exception types only; HTTP via ollama_client

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from config import (
    AGENTS_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    LOGS_DIR,
    RAW_SUGGESTIONS_DIR,
    ROOT_DIR,
    STATE_FILE,
    now_iso,
    today_iso,
)
from utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    read_hard_facts,
    read_wiki_index,
    save_state,
)
from sdk_helpers import (
    FailureClass,
    StderrCapture,
    is_fatal,
    log_sdk_failure,
)

# ── Logging ──────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s  %(levelname)s  %(message)s"
_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    datefmt=_LOG_DATEFMT,
)
log = logging.getLogger("compile")

# Silence noisy library loggers — every Ollama curiosity call would otherwise
# spam an INFO-level "HTTP Request: POST ..." line into compile.log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

LOGS_DIR.mkdir(parents=True, exist_ok=True)
_compile_log_file = LOGS_DIR / "compile.log"
_compile_errors_file = LOGS_DIR / "compile-errors.log"
_log_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

_file_handler = logging.FileHandler(_compile_log_file, encoding="utf-8")
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_file_handler)

_error_handler = logging.FileHandler(_compile_errors_file, encoding="utf-8")
_error_handler.setFormatter(_log_formatter)
_error_handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(_error_handler)

from wiki_config import CONFIG  # noqa: E402
from prompts import render  # noqa: E402
import ollama_client  # noqa: E402

CURIOSITY_MODEL = CONFIG.models.curiosity_model


def _is_email_source(source_path: str) -> bool:
    """Check if a source file contains email scanner data."""
    return "email" in source_path.lower() or "thunderbird" in source_path.lower()


def _read_rules_overview() -> str:
    """Read the Thunderbird rules overview if it exists."""
    overview = ROOT_DIR / "raw" / "notes" / "email" / "thunderbird-rules-overview.md"
    if overview.exists():
        return overview.read_text(encoding="utf-8")
    return "(No rules overview found. Run: thunderbird-rules.py --export)"


def _read_procmail_config() -> str:
    """Read current procmail config from server if available."""
    try:
        import sys
        sys.path.insert(0, str(ROOT_DIR / "scripts"))
        from importlib import import_module
        tb = import_module("thunderbird-rules")
        config = tb.get_procmail_config()
        if config:
            return config
    except Exception:
        pass
    return "(Procmail config not available)"


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


async def compile_file(source: Path, dry_run: bool = False, prefix: str = "") -> dict | None:
    """Compile a single source file into wiki articles.

    Returns usage/cost info dict, or None on failure.
    """
    rel_path = str(source.relative_to(ROOT_DIR))
    badge = _category_badge(rel_path)
    log.info("%s[%s] %s", prefix, badge, rel_path)

    if dry_run:
        log.info("  [dry-run] Would compile %s", rel_path)
        return {"_skipped": "dry_run"}

    # Read source content
    source_content = source.read_text(encoding="utf-8")
    if not source_content.strip():
        log.warning("  Skipping empty file: %s", rel_path)
        return {"_skipped": "empty"}

    # Read current wiki state
    agents_md = ""
    if AGENTS_FILE.exists():
        agents_md = AGENTS_FILE.read_text(encoding="utf-8")

    index_md = read_wiki_index()
    today = today_iso()
    now = now_iso()

    prompt = render(
        "compile_main",
        agents_md=agents_md,
        facts_md=read_hard_facts(),
        index_md=index_md,
        source_path=rel_path,
        source_content=source_content,
        today=today,
        now=now,
    )

    # Run the agent with file editing tools
    total_input_tokens = 0
    total_output_tokens = 0
    result_text = ""
    started = time.time()
    capture = StderrCapture()

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
                permission_mode="acceptEdits",
                max_turns=30,
                system_prompt=render("compile_main_system"),
                setting_sources=[],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                total_input_tokens += message.usage.get("input_tokens", 0)
                total_output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result
    except Exception as exc:
        failure = log_sdk_failure(
            log,
            label="compile_file",
            source=rel_path,
            model=CONFIG.models.compile_model,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=exc,
        )
        return {"_failure": failure}

    elapsed = time.time() - started
    # Estimate cost (Claude Opus 4.6 pricing: $5/M input, $25/M output)
    cost = (total_input_tokens * 5.0 + total_output_tokens * 25.0) / 1_000_000
    log.info(
        "  ✓ %.1fs · in:%s out:%s ($%.4f)",
        elapsed,
        f"{total_input_tokens:,}",
        f"{total_output_tokens:,}",
        cost,
    )

    return {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": cost,
        "result": result_text,
    }


# ── Suggestion pass ──────────────────────────────────────────────────

async def maybe_generate_suggestions(source: Path, dry_run: bool = False) -> None:
    """If the source is email data, run a suggestion pass."""
    rel_path = str(source.relative_to(ROOT_DIR))
    if not _is_email_source(rel_path):
        return

    log.info("  Suggestion pass for %s", rel_path)

    if dry_run:
        log.info("  [dry-run] Would run suggestion pass")
        return

    RAW_SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)

    source_content = source.read_text(encoding="utf-8")
    rules_overview = _read_rules_overview()
    index_md = read_wiki_index()

    procmail_config = _read_procmail_config()

    accounts_inline = ", ".join(
        f"{name} = {info.get('email', '')}" for name, info in CONFIG.personal.accounts.items()
    ) or "(none configured)"

    prompt = render(
        "compile_suggestion",
        rules_overview=rules_overview,
        procmail_config=procmail_config,
        source_path=rel_path,
        source_content=source_content,
        index_md=index_md,
        today=today_iso(),
        primary_account=CONFIG.personal.primary_account,
        email_accounts_inline=accounts_inline,
    )

    started = time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                allowed_tools=["Read", "Write", "Glob"],
                permission_mode="acceptEdits",
                max_turns=10,
                system_prompt=render("compile_suggestion_system"),
                setting_sources=[],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, ResultMessage):
                log.info("  Suggestions: %s", message.result[:200])
    except Exception as exc:
        log_sdk_failure(
            log,
            label="suggestion_pass",
            source=rel_path,
            model=CONFIG.models.compile_model,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=exc,
        )


# ── Curiosity pass ──────────────────────────────────────────────────

def _get_recently_compiled_articles() -> str:
    """Get articles updated today (likely just compiled)."""
    today = today_iso()
    articles = []
    for subdir in ["concepts", "connections", "people", "projects"]:
        d = KNOWLEDGE_DIR / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            if f"updated: {today}" in content or f"created: {today}" in content:
                articles.append(f"### {f.relative_to(KNOWLEDGE_DIR)}\n\n{content[:500]}")
    return "\n\n".join(articles) if articles else "(No articles updated today)"


async def maybe_generate_curiosity_requests(source: Path) -> None:
    """Detect knowledge gaps and write deep-scan requests to raw/requests/."""
    if not CONFIG.features.curiosity_loop:
        return

    rel_path = str(source.relative_to(ROOT_DIR))
    source_content = source.read_text(encoding="utf-8")

    # Only run curiosity on substantial sources (not tiny deltas)
    if len(source_content) < CONFIG.limits.curiosity_min_source_chars:
        return

    index_md = read_wiki_index()
    compiled_articles = _get_recently_compiled_articles()

    folder_paths = [f["path"] for f in CONFIG.personal.email_folders if f.get("path")]
    if not folder_paths:
        log.info("  Curiosity: no personal.email_folders configured, skipping")
        return
    folder_listing = "\n".join(
        f"- {f['path']} — {f.get('desc', '')}".rstrip(" —")
        for f in CONFIG.personal.email_folders
    )

    prompt = render(
        "compile_curiosity",
        index_md=index_md,
        source_path=rel_path,
        source_content=source_content[:5000],  # cap to avoid huge prompts
        compiled_articles=compiled_articles[:3000],
        timestamp=now_iso(),  # cache-buster
        primary_account=CONFIG.personal.primary_account,
        email_folders_listing=folder_listing,
    )

    log.info("  Curiosity pass for %s", rel_path)

    account_names = list(CONFIG.personal.accounts.keys()) or [CONFIG.personal.primary_account]
    schema = {
        "type": "object",
        "properties": {
            "gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "folder": {"type": "string", "enum": folder_paths},
                        "account": {"type": "string", "enum": account_names},
                        "rationale": {"type": "string"},
                    },
                    "required": ["topic", "folder", "account", "rationale"],
                },
            },
        },
        "required": ["gaps"],
    }

    try:
        content = ollama_client.chat_schema(
            prompt,
            model=CURIOSITY_MODEL,
            schema=schema,
            timeout=CONFIG.limits.curiosity_timeout_s,
        )
        try:
            parsed = ollama_client.parse_json_lenient(content)
        except json.JSONDecodeError:
            log.warning("  Curiosity: invalid JSON: %s", content[:200])
            return

        if isinstance(parsed, list):
            gaps = parsed
        elif isinstance(parsed, dict):
            gaps = parsed.get("gaps", [])
        else:
            log.info("  Curiosity: unexpected response type")
            return
        if not gaps:
            log.info("  Curiosity: no gaps found")
            return

        non_dict = [g for g in gaps if not isinstance(g, dict)]
        if non_dict:
            log.warning("  Curiosity: dropping %d non-dict gap(s); sample=%r",
                        len(non_dict), non_dict[0])
        gaps = [g for g in gaps if isinstance(g, dict)]
        if not gaps:
            return

        # Write request files
        RAW_REQUESTS_DIR = ROOT_DIR / "raw" / "requests"
        RAW_REQUESTS_DIR.mkdir(parents=True, exist_ok=True)

        for gap in gaps[:CONFIG.limits.curiosity_max_gaps]:
            folder = gap.get("folder", "").strip()
            topic = gap.get("topic", "").strip()
            rationale = gap.get("rationale", "").strip()

            # Skip invalid requests
            if not folder or not topic or not rationale:
                log.info("  Curiosity: skipping (folder=%r, topic=%r, rationale=%r)",
                         folder[:30] if folder else '', topic[:30] if topic else '', rationale[:30] if rationale else '')
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", topic.lower())[:40].strip("-")
            request_path = RAW_REQUESTS_DIR / f"request-{slug}-{today_iso()}.json"

            if request_path.exists():
                continue  # don't overwrite

            request = {
                "type": "email-deep-scan",
                "status": "pending",
                "folder": folder,
                "account": gap.get("account", CONFIG.personal.primary_account),
                "model": gap.get("model", CURIOSITY_MODEL),
                "topic": topic,
                "rationale": gap.get("rationale", ""),
                "source": rel_path,
                "created": now_iso(),
            }
            request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
            log.info("  Curiosity request: %s → %s", topic, folder)

    except httpx.TimeoutException:
        log.warning("  Curiosity: Ollama timeout")
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("  Curiosity: parse error: %s", e)
    except Exception:
        log.exception("  Curiosity pass failed")


# ── Main ─────────────────────────────────────────────────────────────

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
        return

    log.info("Files to compile: %d", len(files))
    for f in files:
        log.info("  %s", f.relative_to(ROOT_DIR))

    if args.dry_run:
        for f in files:
            await compile_file(f, dry_run=True)
        return

    # Ensure knowledge directories exist
    for subdir in ["concepts", "connections", "qa", "people", "projects"]:
        (KNOWLEDGE_DIR / subdir).mkdir(parents=True, exist_ok=True)

    state = load_state()
    total_cost = state.get("total_cost", 0.0)
    cost_at_start = total_cost  # for history-event cost_delta
    compiled_count = 0
    failed_count = 0
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

        prefix = f"[{compiled_count + failed_count + 1}/{cap}] "
        result = await compile_file(source, prefix=prefix)
        if result is not None and "_skipped" in result:
            # Skipped (empty file, dry-run): neither success nor failure.
            # Don't touch counters — preserves the consecutive-failure streak
            # across legitimate skips so abort thresholds reflect real failures.
            continue
        if result is None or "_failure" in result:
            failed_count += 1
            consecutive_failures += 1
            failure = result.get("_failure") if result else None
            if failure is not None:
                recent_failures.append(failure)
                # Fail-fast on auth/model errors — they will repeat identically
                # for every remaining file. Operator must fix config first.
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

        # Success — reset failure streak
        consecutive_failures = 0
        compiled_count += 1
        total_cost += result.get("cost_usd", 0.0)
        run_input_tokens += result.get("input_tokens", 0)
        run_output_tokens += result.get("output_tokens", 0)

        # Suggestion pass for email sources
        await maybe_generate_suggestions(source)

        # Curiosity pass — detect knowledge gaps, generate deep-scan requests
        await maybe_generate_curiosity_requests(source)

        # Update state: mark file as ingested with its hash + persist immediately.
        # Per-file save (not just end-of-loop) so rate-limit aborts, kills, and
        # crashes don't lose the compile work that already succeeded — otherwise
        # the next run would re-compile the same files and re-spend tokens.
        # Iron rule from KNOWLEDGE.md: "no gap between capture and persist".
        rel = str(source.relative_to(ROOT_DIR))
        if "ingested" not in state:
            state["ingested"] = {}
        state["ingested"][rel] = file_hash(source)
        state["total_cost"] = round(total_cost, 4)
        state["last_compile"] = now_iso()
        save_state(state)

    # Final save (idempotent — captures total_cost / last_compile if loop had
    # zero successes and the per-file save above was never reached).
    state["total_cost"] = round(total_cost, 4)
    state["last_compile"] = now_iso()
    save_state(state)

    # Append-only history event so Dashboard P2 charts can render time series.
    if compiled_count > 0:
        from utils import append_history
        append_history(
            "compile",
            articles_total=len(list_wiki_articles()),
            compiled_this_run=compiled_count,
            failed_this_run=failed_count,
            cost_delta=round(total_cost - cost_at_start, 4),
            cost_total=state["total_cost"],
        )

    outcome = f"ABORTED ({abort_reason or 'unknown'})" if aborted else "complete"
    pending = len(files) - compiled_count - failed_count
    elapsed_min, elapsed_sec = divmod(int(time.time() - run_started), 60)
    run_cost = (run_input_tokens * 5.0 + run_output_tokens * 25.0) / 1_000_000
    log.info("─── compilation %s ───", outcome)
    log.info(
        "  files:   %d done · %d failed · %d pending of %d candidates",
        compiled_count, failed_count, pending, len(files),
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


if __name__ == "__main__":
    asyncio.run(main())
