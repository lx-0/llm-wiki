"""Dream-cycle: periodic cross-time re-synthesis of entity pages (M014 MVP).

Where `compile.py` is per-file distillation (one substrate file → one or more
knowledge/ updates), dream-cycle is cross-time synthesis: it picks ONE entity
(person / project / area), greps all substrate mentioning that entity (or
naming it as `author:`), and rewrites the entity's State block + appends to
Timeline from the full corpus.

The cross-time view surfaces recurring themes, drifting roles, and emerging
concept-clusters that per-file compile cannot see (each compile pass sees ONE
file + index.md).

CLI surface:

    wiki dream-entity <slug>            # re-synthesize one entity
    wiki dream --all-entities           # sweep everyone, respecting cooldown
    wiki dream-entity <slug> --dry-run  # print corpus size, no SDK call

Piggyback wiring: see `core/piggybacks.py:_BUILTIN_PIGGYBACK_TASKS["dream_cycle"]`.
The piggyback shells out to `dream.py piggyback`, which sweeps the N
most-overdue entities under the per-run token cap
(`CONFIG.limits.dream_cycle_max_tokens_per_run`).

Resource gates (real, hard, no silent skips):

  - Per-entity size: `CONFIG.limits.dream_entity_max_prompt_chars`. Pre-flight
    prompt-char check; reject if the prompt exceeds it (context-overflow guard).
  - Per-run tokens (piggyback / --all): `CONFIG.limits.dream_cycle_max_tokens_per_run`.
    Stop sweeping once cumulative real tokens cross the cap.

Cooldown: `CONFIG.scheduling.dream_cooldown_days` (default 7). Entities with
`last_synthesized_at:` newer than that are skipped.

Provider: Claude Agent SDK only — never Ollama. (See feedback memory
`feedback_no_silent_provider_fallback`.)

Modules: this file is the cycle — one entity's synthesis, the sweep, the CLI.
`dream_model.py` holds the entity model + cooldown, `dream_corpus.py` the corpus
one synthesis reads (+ the activation and backoff side-state), `dream_priority.py`
the M017 sweep priority.
"""

from __future__ import annotations

import os

os.environ.setdefault("CLAUDE_INVOKED_BY", "dream")

import argparse
import asyncio
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from claude_agent_sdk import query

from core import frontmatter
from core.config import CONFIG
from core.console import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_RESET,
    C_YELLOW,
    ConsoleFormatter,
    say,
    setup_console_logging,
)
from core.errors import swallow
from core.paths import KNOWLEDGE_DIR, LOG_FILE, ROOT_DIR
from core.prompts import build_output_language_instruction, render
from core.sdk_helpers import SdkCallSpec, WriteScope, run_sdk_query
from core.utils import append_history, now_iso, today_iso
from dream_corpus import (
    CorpusBreakdown,
    _clear_insufficient_corpus,
    _record_insufficient_corpus,
    _stamp_last_dreamed_at,
    collect_corpus_tiered,
    render_corpus_block_tiered,
)
from dream_model import EntityRef, _last_synth_age_days, _resolve_entity, is_within_cooldown
from dream_priority import _select_for_sweep, build_sweep_candidates, list_candidates


class _DreamFormatter(ConsoleFormatter):
    """dream.py-specific colorization on top of the generic formatter.

    Mirrors the per-CLI subclass pattern compile.py uses. Patterns dream owns:

      - per-entity header `▶ [N/M] dream-entity <slug>` → bold cyan, slug yellow
      - contextual info lines (dim, like compile's dispatch tier):
          `  entity=X kind=Y — corpus: T1=...`     (corpus breakdown)
          `  prompt: N chars (X KB) — estimated …`  (pre-flight)
          `  invoking <model> (max_turns=…)`         (execution start)
          `  stamped last_dreamed_at on …`           (housekeeping)
      - termination notes:
          `Reached --limit=N; stopping`              (dim, soft signal)
          `Per-run token cap reached …`              (yellow-ish, soft warn)

    Everything else falls through to the generic colorization (✓/✗,
    bare/parenthesised costs, elapsed, tokens, section banners,
    WARNING/ERROR level labels).
    """

    _HEADER_RE = re.compile(r"^▶\s+\[(\d+/\d+)\]\s+(dream-entity)\s+(\S+)$")
    _DIM_INFO_RES = (
        re.compile(r"^\s+entity=\S+\s+kind="),
        re.compile(r"^\s+prompt:\s+\d+\s+chars"),
        re.compile(r"^\s+invoking\s+claude-"),
        re.compile(r"^\s+stamped\s+last_dreamed_at\s+on\s+\d+"),
    )
    _LIMIT_RE = re.compile(r"^(Reached --limit=\d+|Per-run token cap reached)")

    def _format_message_extras(self, msg: str) -> str | None:
        if mh := self._HEADER_RE.match(msg.strip()):
            pos, action, slug = mh.group(1), mh.group(2), mh.group(3)
            return f"{C_BOLD}{C_CYAN}▶ [{pos}] {action} {C_YELLOW}{slug}{C_RESET}"
        for rx in self._DIM_INFO_RES:
            if rx.match(msg):
                # Dim the whole line but keep cost-amount tier colors inside —
                # apply generic cost regex AFTER the dim wrap.
                dimmed = f"{C_DIM}{msg}{C_RESET}"
                return self._colorize_cost(dimmed)
        if self._LIMIT_RE.match(msg):
            return f"{C_DIM}{msg}{C_RESET}"
        return None


log = logging.getLogger("dream")


# ── Outcome type + exit-code contract ─────────────────────────────
#
# Mirrors the shipped M026 CompileOutcome pattern (DECISIONS.md 2026-05-23):
# a typed per-entity outcome whose `kind` string is classified into a status
# in ONE place, and whose CLI exit code is derived in ONE place — instead of
# the old 6-value magic string mapped to exit codes divergently across the
# entity / sweep / piggyback branches (per_call_timeout + piggyback
# prompt_too_large both exited 0, invisible to piggyback_runner's rc→status
# derivation — a real monitoring blindspot).

DreamStatus = Literal["synthesized", "skipped", "failed"]

# Benign no-ops (exit 0): nothing to synthesize, a designed digests-only skip,
# or a dry run.
_DREAM_SKIP_KINDS: frozenset[str] = frozenset({"no_substrate", "no_entity_substrate", "dry_run"})
# Real problems (nonzero exit): each MUST surface so an unattended piggyback
# records `failed:<rc>` in piggyback-state.json rather than a false `ok`.
_DREAM_FAILURE_KINDS: frozenset[str] = frozenset(
    {"prompt_too_large", "per_call_timeout", "sdk_failure"}
)

# The single exit-code table. A kind absent here is a clean exit 0. per-call
# timeout is 6 (was 0 everywhere — the blindspot); prompt_too_large 3 and
# sdk_failure 4 keep their historical entity-branch codes.
_DREAM_EXIT_CODES: dict[str, int] = {
    "prompt_too_large": 3,
    "sdk_failure": 4,
    "per_call_timeout": 6,
}


def classify_dream_kind(kind: str | None) -> DreamStatus:
    """Map an outcome kind string to its typed status. ``None`` = synthesized."""
    if kind is None:
        return "synthesized"
    if kind in _DREAM_FAILURE_KINDS:
        return "failed"
    return "skipped"


@dataclass
class DreamOutcome:
    entity: EntityRef
    corpus_count: int
    corpus_chars: int
    actual_cost_usd: float
    input_tokens: int
    output_tokens: int
    sdk_result_text: str
    # None = synthesized; else a skip kind (_DREAM_SKIP_KINDS) or a failure
    # kind (_DREAM_FAILURE_KINDS). Replaces the former `skipped` magic string.
    kind: str | None = None
    elapsed_s: float = 0.0
    # True when the agent ran but returned the INSUFFICIENT_CORPUS sentinel —
    # a designed no-op that feeds the per-entity backoff (see
    # is_within_insufficient_backoff).
    insufficient_corpus: bool = False

    @property
    def status(self) -> DreamStatus:
        return classify_dream_kind(self.kind)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    @property
    def exit_code(self) -> int:
        return _DREAM_EXIT_CODES.get(self.kind or "", 0)


def dream_exit_code(outcomes: DreamOutcome | list[DreamOutcome]) -> int:
    """Highest-severity CLI exit code across one or more outcomes (0 = clean).

    The single source of truth every dream CLI branch routes through, so a
    failure kind can never again map to a nonzero exit on one path and 0 on
    another."""
    if isinstance(outcomes, DreamOutcome):
        outcomes = [outcomes]
    return max((o.exit_code for o in outcomes), default=0)


# ── Pure pre/post-SDK decision functions ──────────────────────────
#
# Extracted from dream_entity's async monolith so the deterministic gate/trim
# and outcome classification are table-testable WITHOUT an SDK mock or the
# module-global monkeypatch block. They take the assembled corpus / stat
# snapshots as parameters and read no globals.


def pre_sdk_skip(breakdown: CorpusBreakdown, *, require_entity_substrate: bool) -> str | None:
    """Deterministic pre-SDK skip decision — inspects the assembled corpus
    only. Returns a skip-kind string, or None to proceed to prompt-building.

    - ``no_substrate``        — the mention-scan found nothing to synthesize.
    - ``no_entity_substrate`` — the only corpus is non-mentioning daily digests
      (a guaranteed INSUFFICIENT_CORPUS no-op that would still bill a full
      prompt-cache write ~$0.80). Skip it for $0. Gated so the operator can
      force a digests-only attempt via
      ``features.dream_require_entity_substrate=false``.
    """
    if not breakdown.all_paths:
        return "no_substrate"
    entity_substrate = (
        len(breakdown.tier1_authored) + len(breakdown.tier1_recent) + len(breakdown.tier2_sampled)
    )
    if require_entity_substrate and entity_substrate == 0:
        return "no_entity_substrate"
    return None


@dataclass(frozen=True)
class NoWriteVerdict:
    """Pure post-SDK diagnosis of the entity page after the agent returns.

    ``page_changed`` True = the agent wrote (normal success). When False, the
    write either did not need to happen (``insufficient_corpus`` — a designed
    no-op logged at INFO, feeding the per-entity backoff) or is suspicious (a
    silent write-failure / 'would-change' prose logged at WARNING). ``level``
    is the logging level for the no-op line; ``reason`` the human cause.
    """

    page_changed: bool
    insufficient_corpus: bool
    reason: str
    level: int


_INSUFFICIENT_NOOP_REASON = (
    "agent declared INSUFFICIENT_CORPUS — designed no-op (no synthesizable "
    "claims for this entity in the current corpus)"
)
_SUSPICIOUS_NOOP_REASON = (
    "corpus had no new substrate to incorporate OR agent decided no changes "
    "needed — UNEXPECTED (no INSUFFICIENT_CORPUS sentinel; possible silent "
    "write-failure or 'would-change' prose)"
)


def classify_post_sdk_write(
    *,
    pre_mtime: float,
    pre_size: int,
    post_mtime: float,
    post_size: int,
    result_text: str,
) -> NoWriteVerdict:
    """Deterministic post-SDK write diagnosis — no globals, no I/O.

    A changed page (mtime or size differs) is a normal write. A byte-identical
    page is split into the EXPECTED INSUFFICIENT_CORPUS no-op (INFO) vs. the
    SUSPICIOUS silent no-op (WARNING) the diagnostic exists to catch.
    """
    if pre_mtime != post_mtime or pre_size != post_size:
        return NoWriteVerdict(True, False, "", logging.INFO)
    if "INSUFFICIENT_CORPUS" in (result_text or ""):
        return NoWriteVerdict(False, True, _INSUFFICIENT_NOOP_REASON, logging.INFO)
    return NoWriteVerdict(False, False, _SUSPICIOUS_NOOP_REASON, logging.WARNING)


def _read_facts_md() -> str:
    """Lazy import — pulls in the FACTS_DIR walker."""
    from core.utils import read_hard_facts

    return read_hard_facts()


def _build_owner_block() -> str:
    """Same owner-block rendering as compile.py.

    Imports from `compile_stages.compile` (the pure-library producer-seam
    module) rather than `compile` (the CLI script). Importing the CLI script
    triggers its module-level `setup_console_logging("compile", ...)` call,
    which adds a SECOND stderr handler to root in the running dream process
    — every subsequent log line then double-emits (incident 2026-05-18:
    operator screenshot at 08:02:43 showed `prompt:` and `invoking` lines
    doubled because they fired AFTER the lazy import; earlier lines fired
    BEFORE and stayed single).
    """
    from compile_stages.compile import _build_owner_block as _from_compile

    return _from_compile()


def _build_prompt(
    entity: EntityRef,
    corpus_paths: list[Path],
    *,
    max_turns: int,
    breakdown: CorpusBreakdown,
) -> tuple[str, int]:
    """Render dream_entity.md with the entity + tiered corpus. Returns
    (prompt, total_chars).

    The corpus is always rendered with per-tier section headers so the LLM sees
    the Tier 1 / Tier 2 split (M016) — the flat M014 render is gone.
    """
    current_page = (
        entity.page.read_text(encoding="utf-8")
        if entity.page.exists()
        else "(file does not exist yet — create it from the two-layer template)"
    )
    corpus_block = render_corpus_block_tiered(breakdown)
    corpus_chars = len(corpus_block)
    title = current_page_title(current_page) or entity.title
    prompt = render(
        "dream_entity",
        entity_slug=entity.slug,
        entity_title=title,
        entity_type=entity.type_value,
        entity_page=str(entity.page.relative_to(ROOT_DIR)),
        current_page=current_page,
        corpus_block=corpus_block,
        corpus_count=len(corpus_paths),
        corpus_chars=corpus_chars,
        owner_block=_build_owner_block(),
        facts_md=_read_facts_md(),
        max_turns=max_turns,
        today=today_iso(),
        now=now_iso(),
        entity_link=entity.link,
        output_language_instruction=build_output_language_instruction(
            CONFIG.personal.output_language
        ),
    )
    return prompt, len(prompt)


def _build_prompt_within_budget(
    entity: EntityRef,
    breakdown: CorpusBreakdown,
    *,
    max_turns: int,
    max_chars: int,
) -> tuple[str, int, CorpusBreakdown, int]:
    """Build the prompt; if it overruns ``max_chars``, trim the corpus to fit.

    The corpus is bounded by *file count* (tier caps) but not by *chars*, so a
    high-file-count entity (e.g. ytstack: 52 Tier-1 + 50 Tier-2) can assemble a
    prompt past the budget and previously failed terminally (PROMPT_TOO_LARGE →
    entity never synthesized). Instead, drop the lowest-value substrate until it
    fits: Tier 2 first (sampled older substrate, already score-sorted so the
    tail is least valuable), then the oldest of Tier-1-recent. Tier-1 authored +
    daily digests are load-bearing and never dropped — if the prompt is *still*
    over budget after exhausting the droppable tiers, the caller hard-fails.

    Returns ``(prompt, prompt_chars, trimmed_breakdown, dropped_count)``.
    """
    prompt, prompt_chars = _build_prompt(
        entity, breakdown.all_paths, max_turns=max_turns, breakdown=breakdown
    )
    if max_chars <= 0 or prompt_chars <= max_chars:
        return prompt, prompt_chars, breakdown, 0

    tier2 = list(breakdown.tier2_sampled)
    recent = list(breakdown.tier1_recent)
    dropped = 0
    work = breakdown
    while prompt_chars > max_chars and (tier2 or recent):
        # Adaptive batch: estimate how many trailing files to drop to cover the
        # overrun in one rebuild. avg overestimates per-file corpus chars (it
        # folds in fixed prompt overhead), so the batch is conservative and
        # never over-drops; converges in a handful of rebuilds.
        droppable = len(tier2) + len(recent)
        avg = max(1, prompt_chars // max(1, droppable))
        batch = max(1, min(droppable, (prompt_chars - max_chars) // avg + 1))
        for _ in range(batch):
            if tier2:
                tier2.pop()
            elif recent:
                recent.pop()
            else:
                break
            dropped += 1
        work = replace(breakdown, tier2_sampled=tier2, tier1_recent=recent)
        prompt, prompt_chars = _build_prompt(
            entity, work.all_paths, max_turns=max_turns, breakdown=work
        )
    return prompt, prompt_chars, work, dropped


def current_page_title(page_text: str) -> str | None:
    fm, _body = frontmatter.parse(page_text)
    val = fm.get("title")
    return str(val) if val else None


def _skip_outcome(
    entity: EntityRef,
    kind: str,
    *,
    started: float,
    corpus_count: int = 0,
    corpus_chars: int = 0,
    text: str = "",
) -> DreamOutcome:
    """A zero-spend outcome — the SDK was never called (gate, size cap, dry-run)."""
    return DreamOutcome(
        entity=entity,
        corpus_count=corpus_count,
        corpus_chars=corpus_chars,
        actual_cost_usd=0.0,
        input_tokens=0,
        output_tokens=0,
        sdk_result_text=text,
        kind=kind,
        elapsed_s=time.time() - started,
    )


def _log_corpus_breakdown(entity: EntityRef, breakdown: CorpusBreakdown) -> None:
    log.info(
        "  entity=%s kind=%s — corpus: T1=%d (auth=%d/recent=%d/digests=%d) "
        "T2=%d sampled of %d-file older pool",
        entity.slug,
        entity.kind,
        breakdown.tier1_count,
        len(breakdown.tier1_authored),
        len(breakdown.tier1_recent),
        len(breakdown.tier1_digests),
        breakdown.tier2_count,
        breakdown.tier2_pool_size,
    )


def _build_entity_prompt(
    entity: EntityRef, breakdown: CorpusBreakdown, *, turns: int, max_chars: int
) -> tuple[str, int, CorpusBreakdown]:
    """The prompt within the char budget, with the trim + size log lines."""
    prompt, prompt_chars, breakdown, dropped = _build_prompt_within_budget(
        entity, breakdown, max_turns=turns, max_chars=max_chars
    )
    if dropped:
        # By-design graceful degrade (M016 sampled-activation already rotates
        # Tier-2 across runs), not an anomaly — INFO so it stays out of the
        # errors-only triage log. Large entities (e.g. the operator's own page)
        # legitimately exceed one context window and trim every run.
        log.info(
            "  corpus over budget — dropped %d lowest-value Tier-2/recent "
            "file(s) to fit the %s-char cap (now %d files, %d chars). "
            "Authored + digests preserved.",
            dropped,
            f"{max_chars:,}",
            len(breakdown.all_paths),
            prompt_chars,
        )
    log.info(
        "  prompt: %d chars (%.1f KB) — max %s chars",
        prompt_chars,
        prompt_chars / 1024,
        f"{max_chars:,}" if max_chars > 0 else "unlimited",
    )
    return prompt, prompt_chars, breakdown


async def _invoke_entity_sdk(
    entity: EntityRef, prompt: str, prompt_chars: int, *, model: str, turns: int
):
    """One harness call owns the mechanics (options assembly, path-scope
    hook, per-message stall timeout, cache-aware usage extraction, LEDGER
    recording, failure diagnostics). The returned input_tokens is the TRUE
    cache-inclusive input — ResultMessage.usage preferred, per-turn
    cache-inclusive fallback (DECISIONS 2026-06-02); summing only the uncached
    delta made healthy calls look like no-ops and false-fired the low-token
    warning.

    Model pick (the caller's `model`): prefer the 1M-context variant because
    dream-entity is inherently a fan-out workload (Reads N corpus files +
    Grep/Glob into knowledge/ → tool-turn ballooning blows the standard 200K
    window mid-stream, surfacing as the silent kind=unknown exit-1 documented
    in KNOWLEDGE.md "tool-turn ballooning"). Fall back to compile_model if
    dream_model is explicitly disabled by setting it to ""."""
    return await run_sdk_query(
        prompt,
        SdkCallSpec(
            label=f"dream_entity:{entity.slug}",
            logger=log,
            model=model,
            cwd=ROOT_DIR,
            max_turns=turns,
            system_prompt=render("dream_entity_system"),
            setting_sources=("project",),
            # Path-scope: see compile_stages/compile.py — same swap, same
            # fix; the legacy glob shape stays one config flip away.
            allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
            write_scope=WriteScope(
                roots=(ROOT_DIR / "knowledge", LOG_FILE),
                legacy_allowed_tools=(
                    "Read",
                    "Glob",
                    "Grep",
                    "Write(knowledge/**)",
                    "Edit(knowledge/**)",
                ),
            ),
            stall_timeout_s=CONFIG.limits.dream_per_call_timeout_s,
            source=str(entity.page.relative_to(ROOT_DIR)),
            input_chars=prompt_chars,
        ),
        query_fn=query,
    )


def _failure_outcome(
    entity: EntityRef, sdk, *, corpus_count: int, prompt_chars: int, started: float
) -> DreamOutcome:
    """The outcome of a failed SDK call: a per-call timeout or an SDK failure."""
    elapsed = time.time() - started
    if sdk.failure.kind == "timeout":
        return DreamOutcome(
            entity=entity,
            corpus_count=corpus_count,
            corpus_chars=prompt_chars,
            actual_cost_usd=sdk.cost_usd,
            input_tokens=sdk.input_tokens,
            output_tokens=sdk.output_tokens,
            sdk_result_text=(
                f"per-call timeout after {sdk.elapsed_s:.1f}s (msg_count={sdk.message_count})"
            ),
            kind="per_call_timeout",
            elapsed_s=elapsed,
        )
    log.error(
        "  dream_entity ✗ failed after %.1fs (last_message_count=%d): kind=%s",
        sdk.elapsed_s,
        sdk.message_count,
        sdk.failure.kind,
    )
    return DreamOutcome(
        entity=entity,
        corpus_count=corpus_count,
        corpus_chars=prompt_chars,
        actual_cost_usd=sdk.cost_usd,
        input_tokens=sdk.input_tokens,
        output_tokens=sdk.output_tokens,
        sdk_result_text=str(sdk.exc) if sdk.exc is not None else str(sdk.failure),
        kind="sdk_failure",
        elapsed_s=elapsed,
    )


def _page_snapshot(page: Path, *, fallback: tuple[float, int] = (0.0, 0)) -> tuple[float, int]:
    """(mtime, size) of the entity page — the "did the agent write?" witness."""
    try:
        return page.stat().st_mtime, page.stat().st_size
    except OSError:
        return fallback


def _post_sdk_write_check(
    entity: EntityRef, pre: tuple[float, int], post: tuple[float, int], result_text: str
) -> bool:
    """Diagnostic: did the agent actually write to the entity page? Compares
    mtime+size against the pre-SDK snapshot. False positives are harmless
    (operator manually touched the page mid-run); false negatives matter
    (silent agent no-op was the surface the operator asked about — "dream
    nichts in vault schreibt"). Distinguishes the EXPECTED INSUFFICIENT_CORPUS
    no-op from the SUSPICIOUS silent one via the pure classifier (table-tested —
    classify_post_sdk_write) and keeps the insufficient-corpus backoff
    bookkeeping. Returns whether the agent reported an insufficient corpus."""
    verdict = classify_post_sdk_write(
        pre_mtime=pre[0],
        pre_size=pre[1],
        post_mtime=post[0],
        post_size=post[1],
        result_text=result_text,
    )
    if not verdict.page_changed:
        log.log(
            verdict.level,
            "  agent finished without modifying %s — %s. Page byte-identical to pre-run.",
            str(entity.page.relative_to(ROOT_DIR)),
            verdict.reason,
        )
        log.log(
            verdict.level,
            "  agent final-message text (%d chars): %s",
            len(result_text or ""),
            (result_text or "(empty)")[:1500].replace("\n", " | "),
        )
        if verdict.insufficient_corpus:
            # Back this entity off so the next sweep doesn't re-burn ~$1 on the
            # same guaranteed no-op (exponential window; cleared on the first
            # successful synthesis). Bookkeeping only — never aborts the run.
            count = _record_insufficient_corpus(entity.slug)
            if count:
                log.info(
                    "  insufficient-corpus backoff for %s → consecutive no-op #%d "
                    "(will be deprioritized in the sweep until new substrate lands).",
                    entity.slug,
                    count,
                )
    else:
        # Real synthesis happened — clear any prior backoff so the entity
        # returns to the normal cadence immediately.
        _clear_insufficient_corpus(entity.slug)
    return verdict.insufficient_corpus


def _warn_if_substrate_unprocessed(
    prompt_chars: int, input_tokens: int, actual_cost: float
) -> None:
    """Suspiciously-low token-count signal. A 60 KB prompt should report tens
    of thousands of TRUE input tokens. `input_tokens` already folds in
    cache_creation + cache_read (see UsageTokens) — the pre-fix gate compared
    only the uncached `usage["input_tokens"]` delta (~12 under prompt caching)
    and false-fired on every healthy call. A genuine early-exit / buffer
    truncation shows near-zero TRUE input AND ~$0 billed cost; require both so
    the diagnostic keeps its teeth without crying wolf."""
    if prompt_chars >= 5000 and input_tokens < 1000 and actual_cost < 0.01:
        log.warning(
            "  SDK reported only %d true input tokens (incl. cache) and $%.4f "
            "cost for a %d-char prompt — substrate-processing did not happen "
            "(CLI early-exit, buffer truncation, or tool-use short-circuit). "
            "Check the SDK result text for clues.",
            input_tokens,
            actual_cost,
            prompt_chars,
        )


def _stamp_corpus(entity: EntityRef, corpus_paths: list[Path]) -> None:
    """M016 — stamp last_dreamed_at on every substrate file that appeared in
    this dream's corpus, in ONE locked store write (the per-file rewrite was
    O(corpus × store-size)). This is the activation-tracking mechanism that
    cycles files through Tier 2 sampling over time. A write failure logs and
    continues — the entity-page Write is the deliverable."""
    to_stamp: list[Path] = []
    for path in corpus_paths:
        # Skip the entity page itself (its own last_synthesized_at is
        # written by the prompt's housekeeping rule). Skip daily/<date>.md
        # digests — they're not entity-specific substrate and would churn
        # mtime on every dream of every entity.
        if path.resolve() == entity.page.resolve():
            continue
        try:
            rel = str(path.relative_to(ROOT_DIR))
        except ValueError:
            continue
        # Skip BOTH the legacy flat daily file (`daily/2026-05-18.md`) AND
        # the per-source rollup captures (`daily/2026-05-18/sessions.md`,
        # `daily/2026-05-18/health.md`, etc — daily/-as-rollup migration
        # 2026-05-15). All are stage-3 distillations or per-source captures
        # that re-rollup every day, so stamping them would churn the state
        # file on every dream run for no informational value.
        if re.fullmatch(r"daily/\d{4}-\d{2}-\d{2}\.md", rel):
            continue
        if re.fullmatch(r"daily/\d{4}-\d{2}-\d{2}/[^/]+\.md", rel):
            continue
        to_stamp.append(path)
    stamped = _stamp_last_dreamed_at(to_stamp)
    if stamped:
        log.info("  stamped last_dreamed_at on %d substrate file(s)", stamped)


def _append_dream_history(
    entity: EntityRef,
    *,
    corpus_count: int,
    prompt_chars: int,
    actual_cost: float,
    input_tokens: int,
    output_tokens: int,
    elapsed: float,
    no_vault_write: bool,
) -> None:
    """Per-entity history event so dashboard + grep can answer "what happened
    on the last dream of entity X?"."""
    with swallow("dream-entity history append", logger=log):
        append_history(
            "dream_entity",
            slug=entity.slug,
            kind=entity.kind,
            corpus_count=corpus_count,
            corpus_chars=prompt_chars,
            cost_usd=round(actual_cost, 4),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            elapsed_s=round(elapsed, 1),
            no_vault_write=no_vault_write,
        )


async def dream_entity(
    entity: EntityRef,
    *,
    dry_run: bool = False,
    max_prompt_chars: int | None = None,
    max_turns: int | None = None,
) -> DreamOutcome:
    """Re-synthesize ONE entity page from the substrate corpus.

    Size gate: pre-flight prompt-char check; on overrun returns a DreamOutcome
    with `kind="prompt_too_large"` and zero spend (the SDK is NEVER called
    when the prompt exceeds the cap — context-overflow guard, not cost).
    """
    started = time.time()
    max_chars = (
        max_prompt_chars
        if max_prompt_chars is not None
        else CONFIG.limits.dream_entity_max_prompt_chars
    )
    turns = max_turns if max_turns is not None else 20

    # M016: tiered corpus. Bounded by construction at ~600 KB total
    # regardless of vault size (the M014 flat-collect path hit context
    # overflow on 475-file alex.md → 2.3 MB).
    breakdown = collect_corpus_tiered(entity)
    _log_corpus_breakdown(entity, breakdown)

    # Deterministic pre-SDK gate (pure, table-tested — see pre_sdk_skip). The
    # log line differs per kind but the DECISION lives in one pure function.
    gate = pre_sdk_skip(
        breakdown,
        require_entity_substrate=CONFIG.features.dream_require_entity_substrate,
    )
    if gate == "no_substrate":
        log.warning(
            "  no substrate mentions %s — nothing to synthesize (skipping)",
            entity.slug,
        )
        return _skip_outcome(entity, "no_substrate", started=started)
    if gate == "no_entity_substrate":
        # The only corpus is non-mentioning daily digests → the agent's quality
        # gate will return INSUFFICIENT_CORPUS without writing, but the SDK call
        # still bills a full prompt-cache write (~$0.80). Skip it for $0.
        log.info(
            "  no entity-specific substrate for %s (only %d non-mentioning "
            "daily digest(s) in corpus) — guaranteed no-op, skipping SDK call "
            "($0 instead of a prompt-cache write). Set "
            "features.dream_require_entity_substrate=false to force.",
            entity.slug,
            len(breakdown.tier1_digests),
        )
        return _skip_outcome(
            entity, "no_entity_substrate", started=started, corpus_count=len(breakdown.all_paths)
        )

    prompt, prompt_chars, breakdown = _build_entity_prompt(
        entity, breakdown, turns=turns, max_chars=max_chars
    )
    corpus_paths = breakdown.all_paths  # reflect any budget trim downstream

    if max_chars > 0 and prompt_chars > max_chars:
        msg = (
            f"PROMPT_TOO_LARGE: entity={entity.slug} prompt={prompt_chars} chars "
            f"> max={max_chars} (corpus={len(corpus_paths)} files, "
            "non-droppable: authored + daily digests alone exceed the cap). "
            "Raise CONFIG.limits.dream_entity_max_prompt_chars or prune "
            "operator-authored substrate."
        )
        log.error("  ✗ %s", msg)
        return _skip_outcome(
            entity,
            "prompt_too_large",
            started=started,
            corpus_count=len(corpus_paths),
            corpus_chars=sum(
                len(p.read_text(encoding="utf-8", errors="replace")) for p in corpus_paths
            ),
            text=msg,
        )

    if dry_run:
        log.info("  --dry-run: would invoke SDK with %d-char prompt", prompt_chars)
        return _skip_outcome(
            entity,
            "dry_run",
            started=started,
            corpus_count=len(corpus_paths),
            corpus_chars=prompt_chars,
            text="(dry-run)",
        )

    # Real SDK call, single attempt — dream is a periodic pass; if it fails, the
    # next pass picks the entity up again. Model pick: see _invoke_entity_sdk.
    model = CONFIG.models.dream_model or CONFIG.models.compile_model
    pre = _page_snapshot(entity.page)  # compared post-SDK: did the agent write?
    log.info("  invoking %s (max_turns=%d, system=dream_entity_system)", model, turns)
    sdk = await _invoke_entity_sdk(entity, prompt, prompt_chars, model=model, turns=turns)
    if sdk.failure is not None:
        return _failure_outcome(
            entity, sdk, corpus_count=len(corpus_paths), prompt_chars=prompt_chars, started=started
        )

    elapsed = time.time() - started
    log.info(
        "  ✓ done in %.1fs · in:%s out:%s ($%.4f)",
        elapsed,
        f"{sdk.input_tokens:,}",
        f"{sdk.output_tokens:,}",
        sdk.cost_usd,
    )
    post = _page_snapshot(entity.page, fallback=pre)
    insufficient_corpus = _post_sdk_write_check(entity, pre, post, sdk.result_text)
    _warn_if_substrate_unprocessed(prompt_chars, sdk.input_tokens, sdk.cost_usd)
    _stamp_corpus(entity, corpus_paths)
    # LEDGER recording happens inside run_sdk_query (cache-inclusive, on
    # every outcome — including the timeout/failure paths above).
    _append_dream_history(
        entity,
        corpus_count=len(corpus_paths),
        prompt_chars=prompt_chars,
        actual_cost=sdk.cost_usd,
        input_tokens=sdk.input_tokens,
        output_tokens=sdk.output_tokens,
        elapsed=elapsed,
        no_vault_write=(post == pre),
    )

    # Web-research post-pass (issue #2) — fires on EVERY successful dream
    # (single-entity, sweep, piggyback), restoring the shipped design after it
    # regressed to the single-entity CLI branch only. Gated internally (feature
    # flag + per-entity opt-in + cooldown) and fail-soft, so it is a no-op on
    # the vast majority of entities. dry-run / gated / failed paths return
    # earlier, so reaching here means a real synthesis attempt completed.
    _maybe_web_research(entity)

    return DreamOutcome(
        entity=entity,
        corpus_count=len(corpus_paths),
        corpus_chars=prompt_chars,
        actual_cost_usd=sdk.cost_usd,
        input_tokens=sdk.input_tokens,
        output_tokens=sdk.output_tokens,
        sdk_result_text=sdk.result_text,
        kind=None,
        elapsed_s=elapsed,
        insufficient_corpus=insufficient_corpus,
    )


# ── Sweep across entities ─────────────────────────────────────────
# Priority + candidate verdicts: dream_priority.py.


async def dream_all_entities(
    *,
    cooldown_days: int | None = None,
    per_entity_max_chars: int | None = None,
    per_run_max_tokens: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    selection_mode: str | None = None,
    seed: int | None = None,
) -> list[DreamOutcome]:
    """Sweep all entities respecting caps + cooldown + M017 priority weighting.

    Selection mode (M017):
      - "probabilistic" (default): weighted-random by priority × age — diverse
      - "greedy": top-N by weight — deterministic, predictable
    """
    cd = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    run_cap = (
        per_run_max_tokens
        if per_run_max_tokens is not None
        else CONFIG.limits.dream_cycle_max_tokens_per_run
    )
    mode = selection_mode or "probabilistic"

    # One place computes every gate verdict (build_sweep_candidates); the sweep
    # only FILTERS here. Skipped-because-backoff entities returned
    # INSUFFICIENT_CORPUS recently — re-running now would re-burn a full SDK
    # call on a guaranteed no-op (a successful synthesis clears it). Cooldown +
    # backoff are both bypassed by an explicit `wiki dream <slug>`.
    all_candidates = build_sweep_candidates(cooldown_days=cd)
    total_entities = len(all_candidates)
    _sweep_rng = random.Random(seed) if seed is not None else random
    candidates: list[tuple[float, EntityRef, str]] = []
    backed_off = 0
    for cand in all_candidates:
        if cand.cooldown_active:
            continue
        if cand.backoff_active:
            backed_off += 1
            continue
        # Selection jitter on the deterministic base weight (priority × age).
        weight = cand.weight * _sweep_rng.uniform(0.85, 1.15)
        candidates.append((weight, cand.entity, cand.source))

    # M017 selection (zero-weight / excluded entities are dropped by _select_for_sweep)
    N = limit if limit is not None else len(candidates)
    ranked = _select_for_sweep(candidates, N, mode, seed=seed)

    seed_label = f" · seed={seed}" if seed is not None else ""
    backoff_label = f", {backed_off} in insufficient-corpus backoff" if backed_off else ""
    log.info(
        "─── dream sweep: %d entities total, %d candidates after cooldown+priority filter"
        "%s (mode=%s, run_cap=%s tok%s) ───",
        total_entities,
        len(ranked),
        backoff_label,
        mode,
        f"{run_cap:,}",
        seed_label,
    )

    results: list[DreamOutcome] = []
    cumulative = 0
    for idx, (_weight, ent, _source) in enumerate(ranked, 1):
        if limit is not None and idx > limit:
            log.info("Reached --limit=%d; stopping", limit)
            break
        if run_cap > 0 and cumulative >= run_cap:
            log.info(
                "Per-run token cap reached (%s >= %s tok) — stopping after %d entities",
                f"{cumulative:,}",
                f"{run_cap:,}",
                idx - 1,
            )
            break
        log.info(
            "▶ [%d/%d] dream-entity %s — weight=%.2f · source: %s",
            idx,
            len(ranked),
            ent.slug,
            _weight,
            _source or "(default)",
        )
        res = await dream_entity(
            ent,
            dry_run=dry_run,
            max_prompt_chars=per_entity_max_chars,
        )
        results.append(res)
        cumulative += res.input_tokens + res.output_tokens

    log.info(
        "─── dream sweep finished: %d entities processed, cumulative %s tok ───",
        len(results),
        f"{cumulative:,}",
    )
    # Append-only history event so dashboard + grep can answer
    # "when did dream-cycle last run, for which entities, at what cost?"
    # Mirrors compile/flush event shape (see core.utils.append_history).
    # Observability is best-effort, never blocks the dream.
    with swallow("dream-sweep history append", logger=log):
        skipped_count = sum(1 for r in results if r.status != "synthesized")
        append_history(
            "dream_sweep",
            entities_processed=len(results),
            entities_total=total_entities,
            candidates_after_filter=len(ranked),
            mode=mode,
            seed=seed,
            cost_delta=round(cumulative, 4),
            skipped=skipped_count,
            picked_slugs=[r.entity.slug for r in results],
        )
    return results


# ── CLI ───────────────────────────────────────────────────────────


def _maybe_web_research(ent: EntityRef) -> None:
    """Fail-soft web-research post-pass after a successful dream. Gated
    internally (feature flag + per-entity opt-in + cooldown). Never raises —
    a web hiccup must not break the dream flow.

    Wired into the ``dream_entity`` success seam so it fires on every path that
    synthesizes an entity — single-entity, sweep, and piggyback alike — which
    is the shipped design (backlog/shipped/dream-web-research.md: "hook after
    dream_entity()"). It reads the module-level ``KNOWLEDGE_DIR`` (not a fresh
    ``core.paths`` import) so tests that monkeypatch the vault root see it too.
    """
    try:
        from web_research import run_web_research

        res = run_web_research(
            ent.page,
            config=CONFIG,
            knowledge_dir=KNOWLEDGE_DIR,
            force=False,
        )
        if res.status == "ok" and res.wrote:
            log.info("  web-research: wrote Public Profile block for %s", ent.slug)
        elif res.status == "failed":
            log.warning("  web-research failed for %s: %s", ent.slug, res.reason)
        else:
            log.debug("  web-research skipped for %s: %s", ent.slug, res.reason)
    except Exception:
        log.exception("  web-research post-pass crashed for %s (ignored)", ent.slug)


def _run_web_research_standalone(ent: EntityRef, *, dry_run: bool) -> int:
    """`wiki dream web-research <slug>` — forced refresh (bypasses feature
    flag + opt-in + cooldown; still needs an Exa key)."""
    from core.paths import KNOWLEDGE_DIR
    from web_research import run_web_research

    res = run_web_research(
        ent.page,
        config=CONFIG,
        knowledge_dir=KNOWLEDGE_DIR,
        force=True,
        dry_run=dry_run,
    )
    if res.status == "ok":
        if dry_run and res.block:
            say(res.block)
        else:
            log.info("Wrote Public Profile block for %s", ent.slug)
        return 0
    if res.status == "failed":
        log.error("web-research failed for %s: %s", ent.slug, res.reason)
        return 4
    log.warning("web-research skipped for %s: %s", ent.slug, res.reason)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """The `wiki dream` argv surface: entity / web-research / sweep / piggyback /
    list-candidates (the oracle pins `--help`; the routing lives in `_async_main`)."""
    parser = argparse.ArgumentParser(description="Dream-cycle entity re-synthesis (M014)")
    sub = parser.add_subparsers(dest="cmd")

    p_one = sub.add_parser("entity", help="Re-synthesize one entity by slug")
    p_one.add_argument("slug", help="Entity slug (e.g. alex, emmett, yesterday-os)")
    p_one.add_argument(
        "--dry-run", action="store_true", help="Print prompt + estimate, no SDK call"
    )
    p_one.add_argument(
        "--max-chars", type=int, default=None, help="Override per-entity prompt-char cap"
    )
    p_one.add_argument("--max-turns", type=int, default=20, help="SDK max_turns budget")
    p_one.add_argument(
        "--ignore-cooldown", action="store_true", help="Skip the last_synthesized_at gate"
    )

    p_wr = sub.add_parser(
        "web-research", help="Public-entity web enrichment for ONE entity (issue #2)"
    )
    p_wr.add_argument("slug", help="Entity slug (a public person)")
    p_wr.add_argument(
        "--dry-run", action="store_true", help="Print the Public Profile block, write nothing"
    )

    p_all = sub.add_parser("sweep", help="Sweep all entities (--all-entities)")
    p_all.add_argument("--dry-run", action="store_true")
    p_all.add_argument("--cooldown-days", type=int, default=None)
    p_all.add_argument("--per-entity-max-chars", type=int, default=None)
    p_all.add_argument("--per-run-max-tokens", type=int, default=None)
    p_all.add_argument("--limit", type=int, default=None, help="Hard cap on entity count this run")
    p_all.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Pin RNG seed for reproducible probabilistic selection (debug aid).",
    )
    p_all.add_argument(
        "--selection-mode",
        choices=["probabilistic", "greedy"],
        default=None,
        help="M017: probabilistic (weighted-random) | greedy (top-N by weight). "
        "Default: probabilistic, as the piggyback runs.",
    )

    p_pb = sub.add_parser("piggyback", help="Piggyback wrapper — runs sweep with config defaults")
    p_pb.add_argument("--limit", type=int, default=None)

    p_lc = sub.add_parser(
        "list-candidates",
        help="M017: show ranked candidate list with priority + age + source breakdown",
    )
    p_lc.add_argument("--cooldown-days", type=int, default=None)
    p_lc.add_argument("--limit", type=int, default=30, help="Top N rows (default 30)")
    p_lc.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    return parser


async def _cmd_entity(args: argparse.Namespace) -> int:
    """`wiki dream entity <slug>`: resolve, honour the cooldown gate, dream once."""
    ent = _resolve_entity(args.slug)
    if ent is None:
        log.error(
            "No entity page found for slug %r under knowledge/{people,projects,areas}/. "
            "Check the slug or create the page first via per-file compile.",
            args.slug,
        )
        return 2
    if not args.ignore_cooldown and is_within_cooldown(ent):
        age = _last_synth_age_days(ent)
        cooldown = CONFIG.scheduling.dream_cooldown_days
        log.info(
            "Skipping %s: last_synthesized_at is %.1f days old < cooldown %dd. "
            "Re-run with --ignore-cooldown to force.",
            ent.slug,
            age or 0.0,
            cooldown,
        )
        return 0
    res = await dream_entity(
        ent,
        dry_run=args.dry_run,
        max_prompt_chars=args.max_chars,
        max_turns=args.max_turns,
    )
    # Web-research post-pass (issue #2) now fires inside dream_entity's
    # success seam — see _maybe_web_research — so it covers sweep +
    # piggyback too, not just this single-entity branch. Exit code via the
    # single dream_exit_code map (per_call_timeout is 6, not the old 0).
    return dream_exit_code(res)


def _print_candidates(rows: list[dict], limit: int) -> None:
    """The `list-candidates` table (the `--json` branch prints the rows raw)."""
    say(f"{'Rank':<5} {'Weight':>8}  {'Prio':>6}  {'Age':>7}  {'Slug':<40} Source")
    say("-" * 110)
    for i, r in enumerate(rows[:limit], 1):
        age = f"{r['age_days']}d" if r["age_days"] is not None else "never"
        flags = []
        if r["excluded"]:
            flags.append("EXCLUDED")
        if r["cooldown_active"]:
            flags.append("cooldown")
        if r["backoff_active"]:
            flags.append("backoff")
        flag = (" " + " ".join(flags)) if flags else ""
        say(
            f"{i:<5} {r['weight']:>8.2f}  {r['priority']:>6.2f}  {age:>7}  {r['slug']:<40} {r['source']}{flag}"
        )
    if len(rows) > limit:
        say(f"... and {len(rows) - limit} more (raise --limit to see)")


async def _async_main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.cmd == "entity":
        return await _cmd_entity(args)

    if args.cmd == "web-research":
        ent = _resolve_entity(args.slug)
        if ent is None:
            log.error("No entity page found for slug %r.", args.slug)
            return 2
        return _run_web_research_standalone(ent, dry_run=args.dry_run)

    if args.cmd == "sweep":
        results = await dream_all_entities(
            cooldown_days=args.cooldown_days,
            per_entity_max_chars=args.per_entity_max_chars,
            per_run_max_tokens=args.per_run_max_tokens,
            limit=args.limit,
            dry_run=args.dry_run,
            selection_mode=args.selection_mode,
            seed=getattr(args, "seed", None),
        )
        # Nonzero exit if any entity hit a real failure — prompt-too-large,
        # per-call timeout, or SDK failure. Same dream_exit_code map as the
        # entity branch, so a hung-then-aborted unattended dream can no longer
        # record a false `ok` in piggyback-state.json.
        return dream_exit_code(results)

    if args.cmd == "piggyback":
        # M017: piggyback uses probabilistic mode by default (diversity over
        # time, every eligible entity eventually selected, biased toward
        # high-weight). Operator can override per-invocation via `sweep
        # --selection-mode greedy`.
        results = await dream_all_entities(limit=args.limit, selection_mode="probabilistic")
        # Same single exit-code map — a per_call_timeout or prompt_too_large in
        # an unattended piggyback now surfaces as failed:<rc> (was `ok`).
        return dream_exit_code(results)

    if args.cmd == "list-candidates":
        import json as _json

        rows = list_candidates(cooldown_days=args.cooldown_days)
        if args.json:
            say(_json.dumps(rows, indent=2))
            return 0
        _print_candidates(rows, args.limit)
        return 0

    parser.print_help()
    return 1


def main() -> int:
    setup_console_logging("dream", formatter=_DreamFormatter())
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())
