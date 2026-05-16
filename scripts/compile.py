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
import fcntl
import io
import json
import logging
import re
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

from core.paths import AGENTS_FILE, KNOWLEDGE_DIR, LOGS_DIR, LOG_FILE, ROOT_DIR, STATE_DIR, STATE_FILE
from core.utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    now_iso,
    read_hard_facts,
    read_wiki_index,
    read_wiki_index_compact,
    save_state,
    today_iso,
)
from core.sdk_helpers import (
    FailureClass,
    PromptTooLargeError,
    StderrCapture,
    assert_prompt_within_budget,
    is_fatal,
    log_sdk_failure,
)

# ── Logging ──────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s  %(levelname)s  %(message)s"
_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# ANSI escape codes for the colored stderr handler. Empty strings when
# stderr isn't a TTY (piped to a file, captured by CI, etc.) so the
# escape sequences don't leak into log captures.
_TTY = sys.stderr.isatty()
_C_RESET = "\033[0m" if _TTY else ""
_C_DIM = "\033[2m" if _TTY else ""
_C_BOLD = "\033[1m" if _TTY else ""
_C_RED = "\033[31m" if _TTY else ""
_C_GREEN = "\033[32m" if _TTY else ""
_C_YELLOW = "\033[33m" if _TTY else ""
_C_CYAN = "\033[36m" if _TTY else ""


class _ConsoleFormatter(logging.Formatter):
    """Tighter, optionally-colored formatter for stderr console output.

    File handlers keep the verbose ISO-timestamp format for grep-friendly
    archival; this one trims to HH:MM:SS and applies a consistent color
    scheme per line type:

      - per-file header `[N/M] [badge] path`           bold cyan, ▶ marker
      - dispatch line   `  type=X → prompt @ model`    dim
      - success line    `  ✓ Ns · in:N out:N ($X)`     green ✓, dim tokens
      - failure line    `  ✗ ...`                       red ✗
      - curiosity line  `  Curiosity*`                  magenta (different subsystem)
      - section banner  `─── ... ───`                   bold
      - cost in any line                                tiered: dim<$0.05 / plain / yellow>$0.50 / bold-yellow>$1.50
      - badge `[name]` inside header                    yellow
      - elapsed time `Ns`                               dim
    """

    LEVEL_COLOR = {
        "WARNING":  _C_YELLOW,
        "ERROR":    _C_RED,
        "CRITICAL": _C_RED + _C_BOLD,
    }

    _COST_RE = re.compile(r"\(\$(\d+(?:\.\d+)?)\)")
    _HEADER_RE = re.compile(r"^\[(\d+/\d+)\]\s+\[([^\]]+)\]\s+(\S+)$")
    _DISPATCH_RE = re.compile(r"^\s+type=[\w-]+\s+→")
    _CURIOSITY_RE = re.compile(r"^\s+Curiosity[: ]")
    _SUCCESS_RE = re.compile(r"^\s+✓\s")
    _FAILURE_RE = re.compile(r"^\s+✗\s")
    _SECTION_RE = re.compile(r"^─── .+ ───$")
    _ELAPSED_RE = re.compile(r"\b(\d+\.\d+s)\b")
    _TOKENS_RE = re.compile(r"\b(in:[\w.,]+\s+out:[\w.,]+)")

    def _colorize_cost(self, msg: str) -> str:
        def _sub(m: re.Match[str]) -> str:
            amount = float(m.group(1))
            if amount >= 1.50:
                color = _C_BOLD + _C_YELLOW
            elif amount >= 0.50:
                color = _C_YELLOW
            elif amount < 0.05:
                color = _C_DIM
            else:
                return m.group(0)
            return f"({color}${m.group(1)}{_C_RESET})"
        return self._COST_RE.sub(_sub, msg)

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()

        if _TTY:
            # Section banner — full bold (matches log.info("─── compiling N of M …"))
            if self._SECTION_RE.match(msg.strip()):
                msg = f"{_C_BOLD}{msg}{_C_RESET}"
            # Per-file header — full cyan/bold with ▶ marker, badge tinted yellow.
            elif (mh := self._HEADER_RE.match(msg.strip())):
                pos, badge, path = mh.group(1), mh.group(2), mh.group(3)
                msg = (
                    f"{_C_BOLD}{_C_CYAN}▶ [{pos}] "
                    f"{_C_YELLOW}[{badge}]{_C_CYAN} {path}{_C_RESET}"
                )
            # Dispatch line — dim (it's a routing note, not action).
            elif self._DISPATCH_RE.match(msg):
                msg = f"{_C_DIM}{msg}{_C_RESET}"
            # Curiosity engine lines — magenta to distinguish from compile.
            elif self._CURIOSITY_RE.match(msg):
                msg = f"\033[35m{msg}{_C_RESET}"
            # Success/failure inline markers + cost/elapsed/tokens tinting
            # for all remaining lines (incl. ✓ summary lines).
            else:
                msg = msg.replace("✓", f"{_C_GREEN}✓{_C_RESET}")
                msg = msg.replace("✗", f"{_C_RED}✗{_C_RESET}")
                msg = self._colorize_cost(msg)
                msg = self._ELAPSED_RE.sub(f"{_C_DIM}\\1{_C_RESET}", msg)
                msg = self._TOKENS_RE.sub(f"{_C_DIM}\\1{_C_RESET}", msg)

        level_color = self.LEVEL_COLOR.get(record.levelname, "")
        level_text = "" if record.levelname == "INFO" else record.levelname
        level = level_text.ljust(7)
        if level_color and _TTY and level_text:
            level = f"{level_color}{level_text}{_C_RESET}".ljust(
                7 + len(level_color) + len(_C_RESET)
            )

        return f"{_C_DIM}{ts}{_C_RESET}  {level}  {msg}"


class _NoiseFilter(logging.Filter):
    """Drop the high-volume noise lines from console (file handlers keep them).

    The SDK prints "Using bundled Claude Code CLI: <path>" once per compile
    call — at ~100 files/batch that's 100 useless full-path lines on stderr.
    Keep them in the .log archive (the file handlers don't carry this
    filter), drop from interactive console.
    """

    _DROP_SUBSTRINGS = (
        "Using bundled Claude Code CLI:",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self._DROP_SUBSTRINGS)


# Explicit handler setup (replaces basicConfig so we control the stderr
# formatter + filter without competing with the default StreamHandler).
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_console_handler = logging.StreamHandler(sys.stderr)
_console_handler.setFormatter(_ConsoleFormatter())
_console_handler.addFilter(_NoiseFilter())
_root.addHandler(_console_handler)

log = logging.getLogger("compile")

# Silence noisy library loggers — every Ollama curiosity call would otherwise
# spam an INFO-level "HTTP Request: POST ..." line into compile.log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# claude_agent_sdk's internal message reader emits a generic
# `logger.error("Fatal error in message reader: ...")` line BEFORE the
# exception bubbles up to our except block — every CLI exit-1 (max_turns,
# context overflow, kind=unknown, etc.) produces two log records: the SDK's
# alarming-but-uninformative "Fatal error / Check stderr output for details"
# line first, then our own classifier's `kind=max_turns · ...` line with the
# real diagnosis. Our classifier in `compile_file()` already extracts and
# logs everything (final ResultMessage, classified kind, cost burned,
# captured stderr lines), so silencing the SDK's pre-exception ERROR is
# information-loss-free and makes the operator's first-seen error line the
# actual diagnosis instead of generic CLI failure noise.
logging.getLogger("claude_agent_sdk._internal.query").setLevel(logging.CRITICAL)

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

from core.config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402
from core import ollama_client  # noqa: E402

from suggestions.producer import maybe_generate_suggestions  # noqa: E402
from curiosity.producer import maybe_generate_curiosity_requests  # noqa: E402


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

# Substrate-aware prompt dispatch table. Maps frontmatter `type:` value
# to a (prompt_name, max_turns_override) tuple. The default fall-through
# is ("compile_main", None) which uses the heavy dialog-substrate prompt
# at the standard turn budget (12). Per-substrate prompts are tighter
# (calendar = pure metadata extraction, daily = cross-linking only) and
# ship with their own turn budgets matched to the actual workload —
# avoids the max_turns trap that loops compile_main.md on substrates
# without dialog content. Add new entries when a substrate type
# repeatedly hits max_turns / cost_exceeded under compile_main. The
# prompt files live in `prompts/<name>.md` and are loaded via render().
# SubstrateProfile: (prompt_name, max_turns, model_override or None)
# model_override=None falls through to CONFIG.models.compile_model.
SUBSTRATE_PROMPTS: dict[str, tuple[str, int, str | None]] = {
    # Calendar + daily are mechanical Glob/Edit work — no reasoning depth
    # required. Routing to Haiku 4.5 (~6× cheaper than Opus) drops cost
    # from $2-3/file to $0.30-0.50 while keeping the same dispatch.
    # Empirical: 2026-02-26 (dense, 37 link-signals) hit max_turns=8 at
    # $2.38 on Opus → Haiku at 12 turns expected to finish under $0.60.
    "calendar-rollup": ("compile_calendar", 12, "claude-haiku-4-5-20251001"),
    # Daily-digest references more entities than calendar (people +
    # projects + concepts, not just attendees + recurring-concepts).
    # Empirical: 12-turn budget hit at $1.14 (Opus) with 2 entities
    # edited. 20 + Haiku covers digests with up to ~6 mentioned entities
    # well under budget.
    "daily-digest":    ("compile_daily", 20, "claude-haiku-4-5-20251001"),
    # Health-rollup is metric-only frontmatter with a stub body ~99% of
    # days. Falling through to compile_main.md spawned the heavy
    # two-layer carry-forward audit on a file with no dialog → cost
    # exceeded $2-3/file on 2026-05-16. The lean prompt executes the
    # established `concepts/health-rollup-intake-format` policy
    # directly: append to compiled_from + emit one log entry. Operator
    # body-prose branch keeps Timeline-append shape (no State writes).
    # 10 turns: 4 mandatory tool calls (Read+Edit policy article,
    # Read+Edit log.md, dictated by Claude Code's Edit-after-Read
    # safety rule) + final emit = 5 minimum, plus slack for Glob /
    # re-Read / prose-branch Timeline appends. Empirical: budget=6
    # consistently hit max_turns on 2026-05-16 batch.
    "health-rollup":   ("compile_health", 10, "claude-haiku-4-5-20251001"),
    # Screenshot batches: 50-screenshot reports with per-frame summaries
    # + table-of-contents. compile_main.md hit max_turns at $5+/file
    # on 2026-05-15 (49 screenshots → many concept-page Edits). Lean
    # prompt focuses on concept-extraction + source_screenshots tagging.
    # Haiku at 15 turns expected to fit comfortably; the source is
    # routinely 50-100 KB but Haiku 4.5 has 200K context.
    "screenshot-batch": ("compile_screenshots", 20, "claude-haiku-4-5-20251001"),
    # Memory-sync = cross-project AGENTS/CLAUDE.md copies (~200 lines
    # each, 820 in lxw queue → potential $1700+ burn on compile_main).
    # Memory-seed = aggregated per-project memory dumps (~40 lines).
    # Both are substantive but formulaic — extract entities + cross-
    # link to existing concept/project pages, no State writes. Same
    # 15-turn budget as health-rollup since both follow a tight pattern.
    "memory-sync":     ("compile_memories", 20, "claude-haiku-4-5-20251001"),
    "memory-seed":     ("compile_memories", 20, "claude-haiku-4-5-20251001"),
}


# Path-prefix → substrate_key fallback for legacy substrate files that
# don't carry the new `type:` frontmatter yet. Producers SHOULD emit a
# frontmatter type going forward (so SUBSTRATE_PROMPTS lookup hits the
# direct path), but until every existing vault file is backfilled the
# path-pattern fallback keeps compile-dispatch sane. Pattern: matched
# against the source path with `startswith`. Longer-prefix wins on
# overlap; iterate from most-specific to least-specific.
_SUBSTRATE_PATH_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("raw/notes/screenshots/screenshots-", "screenshot-batch"),
)


def _substrate_key(source_content: str, rel_path: str) -> str | None:
    """Dispatch key for SUBSTRATE_PROMPTS: frontmatter type, else path-pattern."""
    t = _frontmatter_type(source_content)
    if t:
        return t
    for prefix, key in _SUBSTRATE_PATH_FALLBACKS:
        if rel_path.startswith(prefix):
            return key
    return None


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


def _frontmatter_type(content: str) -> str | None:
    """Extract `type:` from a leading YAML frontmatter block, or None.

    Regex-only — sufficient for the single scalar field we need and avoids
    pulling a yaml dependency into the compile hot path. Tolerates quoted
    values and trailing whitespace; matches the first `type:` inside the
    leading `---` … `---` fence, not anywhere else in the body.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    m = re.search(r"^type:\s*[\"']?([\w-]+)[\"']?\s*$", block, re.MULTILINE)
    return m.group(1) if m else None


async def compile_file(
    source: Path,
    dry_run: bool = False,
    prefix: str = "",
    *,
    force: bool = False,
) -> dict | None:
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
        return {"_skipped": "dry_run"}

    # Read source content
    source_content = source.read_text(encoding="utf-8")
    if not source_content.strip():
        log.warning("  Skipping empty file: %s", rel_path)
        return {"_skipped": "empty"}

    # Substrate-type skip: some substrates are structurally a poor fit for
    # the generic compile_main.md prompt (calendar metadata has no dialog
    # to extract commitments from, but each attendee still triggers the
    # full two-layer carry-forward audit → max_turns loops at $5-10/file).
    # Listed types are collected but not compiled until a dedicated
    # substrate prompt exists. Operator can force-compile with
    # `wiki compile --file <path>` to bypass.
    skip_type = _frontmatter_type(source_content)
    if (
        not force
        and skip_type is not None
        and skip_type in CONFIG.limits.compile_skip_substrate_types
    ):
        log.info(
            "  skipping: type=%s is in compile_skip_substrate_types "
            "(use `wiki compile --file <path>` to force)",
            skip_type,
        )
        return {"_skipped": f"substrate_type_excluded_{skip_type}"}

    # Read current wiki state
    agents_md = ""
    if AGENTS_FILE.exists():
        agents_md = AGENTS_FILE.read_text(encoding="utf-8")

    index_md = read_wiki_index_compact()
    today = today_iso()
    now = now_iso()

    facts_md = read_hard_facts()

    # Substrate-aware prompt dispatch. Different substrates need
    # different compile shapes; routing them all through compile_main.md
    # (designed for dialog-rich transcripts with State+Timeline carry-
    # forward) burns money on max_turns loops for metadata-only or
    # already-distilled substrates. See KNOWLEDGE.md "substrate-aware
    # compile architecture (P2)". Each entry maps frontmatter `type:`
    # to a (prompt_name, max_turns_override) tuple. Unmapped types fall
    # through to compile_main + default max_turns.
    # Dispatch key: frontmatter `type:` if present, else path-pattern
    # fallback for legacy substrates (e.g. screenshot batches that
    # predate the type-frontmatter migration). source_type is also kept
    # for downstream force-long-context checks (which still match on
    # YAML type only).
    source_type = _frontmatter_type(source_content)
    dispatch_key = _substrate_key(source_content, rel_path)
    substrate_prompt, substrate_max_turns, substrate_model = SUBSTRATE_PROMPTS.get(
        dispatch_key or "", ("compile_main", None, None),
    )
    if substrate_prompt != "compile_main":
        # Truncate model id for readability: "claude-haiku-4-5-20251001"
        # → "haiku-4-5". Keep the full id in the underlying records.
        short_model = ""
        if substrate_model:
            m = re.match(r"claude-(haiku|sonnet|opus)-(\d+-\d+)", substrate_model)
            short_model = f" @ {m.group(1)}-{m.group(2)}" if m else f" @ {substrate_model}"
        log.info("  type=%s → %s%s", source_type, substrate_prompt, short_model)
    prompt = render(
        substrate_prompt,
        agents_md=agents_md,
        facts_md=facts_md,
        index_md=index_md,
        source_path=rel_path,
        source_content=source_content,
        today=today,
        now=now,
    )

    # Pre-flight guard: assembled prompt + later tool-turns must fit Opus's
    # 200K-token window. Without this a 138 KB gmeet transcript loops on
    # Read/Grep until the SDK dies silently with exit-1 / empty stderr after
    # 13 minutes of kind=unknown (see KNOWLEDGE.md). Surfaces the bloated
    # component to the operator instead.
    try:
        assert_prompt_within_budget(
            len(prompt),
            CONFIG.limits.compile_max_prompt_chars,
            label=f"compile_file {rel_path}",
            breakdown={
                "compact index": len(index_md),
                "AGENTS.md": len(agents_md),
                "hard facts": len(facts_md),
                "source": len(source_content),
            },
        )
    except PromptTooLargeError as exc:
        log.error("  %s", exc)
        return {"_skipped": "prompt_too_large"}

    # Pick the model. Large sources auto-upgrade to the 1M-context variant
    # because the standard 200K window dies silently mid-stream once the
    # source + tool-turn reads exceed the window (see KNOWLEDGE.md
    # "tool-turn ballooning"). Operator can pin to the small variant by
    # setting `compile_large_source_model: ""` in config.yaml.
    #
    # The size threshold is necessary but not sufficient: some substrates
    # are small on the surface yet fan out heavily into existing knowledge
    # during compile (daily-digest is the canonical case — <2 KB source
    # references 6+ topics, agent Reads each related article, context
    # overflows mid-stream). Force [1m] up-front for those substrates
    # regardless of size (`compile_force_long_context_types`).
    # Substrate-specific model override (SUBSTRATE_PROMPTS) takes
    # precedence over compile_model default. Used to route lean
    # mechanical prompts (calendar, daily) to Haiku for 6× cost
    # reduction — these don't need Opus reasoning depth.
    # Model precedence (high → low):
    #   1. substrate_model from SUBSTRATE_PROMPTS — dedicated lean prompt
    #      knows its workload, no escalation needed even for big sources.
    #      Haiku 4.5 handles 100KB+ sources at 200K context.
    #   2. force-long-context tier (substrates still on compile_main that
    #      legitimately need [1m]; default list is empty).
    #   3. size-based escalation (50KB+ → [1m]) — only for compile_main
    #      route, since size-fan-out is what blew the 200K window for the
    #      generic prompt.
    #   4. CONFIG.models.compile_model default.
    # Before 2026-05-16-evening, size-escalation overrode substrate_model
    # and bumped lean-prompt files to Opus[1m] anyway → screenshot batch
    # at 64KB hit max_turns at $5+/file with the wrong model.
    model = substrate_model or CONFIG.models.compile_model
    force_long_ctx = (
        source_type is not None
        and source_type in CONFIG.limits.compile_force_long_context_types
        and CONFIG.models.compile_large_source_model
    )
    if substrate_model:
        # Substrate-specific model wins; don't escalate.
        pass
    elif force_long_ctx:
        model = CONFIG.models.compile_large_source_model
        log.info(
            "  type=%s — forcing %s (substrate fans out into knowledge/ during compile)",
            source_type, model,
        )
    elif (
        len(source_content) >= CONFIG.limits.compile_large_source_chars
        and CONFIG.models.compile_large_source_model
    ):
        model = CONFIG.models.compile_large_source_model
        log.info(
            "  large source: %d chars (%.1f KB) — using %s (max_turns=%d)",
            len(source_content), len(source_content) / 1024,
            model, CONFIG.limits.compile_max_turns,
        )

    # Turn budget priority:
    #   1. Per-substrate override from SUBSTRATE_PROMPTS (tight prompts
    #      ship with their own budget — calendar=8, daily=12, etc.)
    #   2. Long-context tier for fan-out substrates still on compile_main
    #      (the old escape hatch — kept for substrates that haven't
    #      gotten dedicated prompts yet but are listed in
    #      compile_force_long_context_types)
    #   3. Default compile_max_turns (12) for everything else
    if substrate_max_turns is not None:
        max_turns_for_call = substrate_max_turns
    elif force_long_ctx:
        max_turns_for_call = CONFIG.limits.compile_max_turns_long_context
    else:
        max_turns_for_call = CONFIG.limits.compile_max_turns

    async def _attempt(model_id: str) -> tuple[dict, FailureClass | None]:
        total_input_tokens = 0
        total_output_tokens = 0
        result_text = ""
        # Capture the final ResultMessage even when the bundled CLI then
        # exit-1s (which it does on `subtype=error_max_turns` and a few
        # other terminal-but-structured agent states). Without this, the
        # exception-handler path below classifies the failure from
        # exception text only and misreports `max_turns` as the opaque
        # `kind=unknown`. See KNOWLEDGE.md.
        final_result: "ResultMessage | None" = None
        started = time.time()
        capture = StderrCapture()
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                    cwd=str(ROOT_DIR),
                    model=model_id,
                    # PATH-SCOPED ALLOWLIST (locked 2026-05-15). Write/Edit
                    # are restricted to `knowledge/**` by tool-pattern. Any
                    # other target path is default-denied by the bundled CLI
                    # without needing a corresponding entry in `disallowed_tools`.
                    # This is a tighter posture than the denylist that
                    # preceded it: substrate (daily/, raw/) routinely
                    # contains literal change-descriptions of engine files
                    # (`.ytstack/*`, `docs/*`, `AGENTS.md`, ...) which the
                    # agent otherwise treated as instructions and executed
                    # against `<vault>/.wiki/`. See KNOWLEDGE.md "Compile
                    # prompt injection via substrate".
                    allowed_tools=[
                        "Read", "Glob", "Grep",
                        "Write(knowledge/**)",
                        "Edit(knowledge/**)",
                    ],
                    permission_mode="acceptEdits",
                    max_turns=max_turns_for_call,
                    system_prompt=render("compile_main_system"),
                    # Pick up the vault's CLAUDE.md (if any) so operator
                    # scope-discipline rules reach the agent. Empty list
                    # killed that signal previously.
                    setting_sources=["project"],
                    stderr=capture.callback,
                ),
            ):
                if isinstance(message, AssistantMessage) and message.usage:
                    total_input_tokens += message.usage.get("input_tokens", 0)
                    total_output_tokens += message.usage.get("output_tokens", 0)
                if isinstance(message, ResultMessage):
                    final_result = message
                    result_text = message.result or ""
        except Exception as exc:
            # Bundled CLI exited non-zero. If a structured ResultMessage
            # arrived just before the exception, it carries the actual
            # terminal state (e.g. `subtype=error_max_turns`) and the cost
            # already burned. Reclassify from that instead of the opaque
            # exception so logs name the real failure kind.
            elapsed = time.time() - started
            if final_result is not None and final_result.is_error:
                cost = final_result.total_cost_usd or 0.0
                kind = "max_turns" if final_result.subtype == "error_max_turns" else "agent_error"
                detail = (
                    f"{final_result.subtype} after {final_result.num_turns} turns "
                    f"({elapsed:.1f}s, ${cost:.4f} burned)"
                )
                if final_result.errors:
                    detail += f" — errors: {'; '.join(final_result.errors)}"
                # Cost guard takes precedence over the structural kind:
                # a max_turns failure at $0.50 should skip-and-flag (cheap
                # loop, batch survives), but at $9.65 should abort the
                # batch so the next dense file doesn't repeat the burn.
                budget = CONFIG.limits.compile_max_cost_per_file_usd
                if budget > 0 and cost > budget:
                    failure = FailureClass(
                        "cost_exceeded",
                        f"${cost:.4f} > budget ${budget:.4f} on {rel_path} (underlying {kind}: {detail})",
                    )
                else:
                    failure = FailureClass(kind, detail)
                log.error(
                    "  compile_file ✗ %s · %s",
                    f"failed after {elapsed:.1f}s — kind={failure.kind}",
                    detail,
                )
                log.error("    source:    %s", rel_path)
                log.error("    model:     %s", model_id)
                log.error("    input:     %d chars (%.1f KB)",
                          len(source_content), len(source_content) / 1024)
                log.error("    cost:      $%.4f burned despite failure", cost)
                if failure.kind == "cost_exceeded":
                    log.error(
                        "    BUDGET EXCEEDED — batch will abort (raise "
                        "`compile_max_cost_per_file_usd` from $%.2f if you "
                        "accept this burn, or add the substrate type to "
                        "`compile_skip_substrate_types`).",
                        budget,
                    )
                capture.dump_to(log)
                return {}, failure
            failure = log_sdk_failure(
                log,
                label="compile_file",
                source=rel_path,
                model=model_id,
                input_chars=len(source_content),
                started=started,
                capture=capture,
                exc=exc,
            )
            return {}, failure

        elapsed = time.time() - started
        # Claude Opus 4.7 pricing: $5/M input, $25/M output
        cost = (total_input_tokens * 5.0 + total_output_tokens * 25.0) / 1_000_000
        # Prefer the ResultMessage's authoritative total_cost_usd if
        # available — it accounts for cache reads + creation tiers that
        # the simple input/output multiplication above ignores.
        if final_result is not None and final_result.total_cost_usd is not None:
            cost = float(final_result.total_cost_usd)
        # Per-file cost guard. Fires on the SUCCESS path too: a "completed"
        # compile that burned $5+ is still a structural smell (typically
        # max_turns-completing-just-barely on a substrate-prompt mismatch).
        # is_fatal()=True for cost_exceeded → batch aborts immediately so
        # subsequent files don't repeat the burn. Operator can raise the
        # knob or skip the substrate type to continue.
        budget = CONFIG.limits.compile_max_cost_per_file_usd
        if budget > 0 and cost > budget:
            log.error(
                "  compile_file ✗ cost_exceeded · $%.4f > budget $%.4f "
                "(elapsed %.1fs, model=%s)",
                cost, budget, elapsed, model_id,
            )
            log.error("    source:    %s", rel_path)
            log.error(
                "    hint:      this file burned beyond the per-file guard. "
                "Likely substrate-prompt mismatch (e.g. dense calendar in "
                "compile_main.md). Skip the type via "
                "`compile_skip_substrate_types`, or raise "
                "`compile_max_cost_per_file_usd` (current: $%.2f) if you "
                "accept the burn.",
                budget,
            )
            return {}, FailureClass(
                "cost_exceeded",
                f"${cost:.4f} > budget ${budget:.4f} on {rel_path}",
            )
        log.info(
            "  ✓ %.1fs · in:%s out:%s ($%.4f)",
            elapsed,
            f"{total_input_tokens:,}",
            f"{total_output_tokens:,}",
            cost,
        )
        return (
            {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cost_usd": cost,
                "result": result_text,
            },
            None,
        )

    success, failure = await _attempt(model)

    # Retry once with the 1M-context variant on the kind=unknown signature
    # of mid-stream context overflow from tool-turn fan-out. Two guards
    # added 2026-05-15 after a rate-limit cascade was misclassified as
    # `cli_crash` (see KNOWLEDGE.md):
    #   - Source-size gate: small sources fail kind=unknown for non-context
    #     reasons (over-eager tool fan-out for new substrate types). The
    #     1M variant doesn't help there and the retry burns an API rate
    #     limit slot.
    #   - Backoff: the immediate retry is what triggered the cascade; the
    #     original call + retry + next file's call inside a 3-second
    #     window all landed in the same rate-limit minute. Sleep clears it.
    long_ctx_model = CONFIG.models.compile_large_source_model
    min_for_retry = CONFIG.limits.compile_retry_long_context_min_source_chars
    if (
        failure is not None
        and failure.kind == "unknown"
        and CONFIG.limits.compile_retry_long_context_on_unknown
        and long_ctx_model
        and model != long_ctx_model
        and len(source_content) >= min_for_retry
    ):
        backoff = CONFIG.limits.compile_failure_backoff_s
        if backoff > 0:
            log.warning(
                "  sleeping %ds before long-context retry (rate-limit cushion)",
                backoff,
            )
            await asyncio.sleep(backoff)
        log.warning(
            "  retrying with long-context model %s after kind=unknown",
            long_ctx_model,
        )
        success, failure = await _attempt(long_ctx_model)
    elif (
        failure is not None
        and failure.kind == "unknown"
        and len(source_content) < min_for_retry
    ):
        log.info(
            "  skipping long-context retry (source %d chars < %d) — "
            "small-source kind=unknown is typically tool-fanout, not context overflow",
            len(source_content), min_for_retry,
        )

    # Skip-and-flag: structural failures with no further retry path.
    # Treats as a survivable skip rather than a hard failure so the batch
    # makes progress; consecutive-failure budget is preserved for genuine
    # systemic outages (rate_limit cascades, auth, network).
    if failure is not None and CONFIG.limits.compile_skip_on_long_context_unknown:
        if failure.kind == "max_turns":
            log.warning(
                "  skipping: max_turns hit (%s) — agent didn't finish within "
                "the turn budget. Bumping `compile_max_turns_long_context` for "
                "this substrate may help; the file is left uncompiled. "
                "Not counted toward consecutive-failure abort.",
                failure.detail,
            )
            return {"_skipped": "max_turns_exhausted"}
        if failure.kind == "unknown":
            if model == long_ctx_model:
                log.warning(
                    "  skipping: kind=unknown on long-context model %s "
                    "— bundled CLI exited 1 with no structured ResultMessage. "
                    "Not counted toward consecutive-failure abort.",
                    model,
                )
                return {"_skipped": "kind_unknown_on_long_context"}
            if len(source_content) < min_for_retry:
                log.warning(
                    "  skipping: small-source kind=unknown with no retry path "
                    "(source %d chars < %d, long-context retry doesn't help here). "
                    "Not counted toward consecutive-failure abort.",
                    len(source_content), min_for_retry,
                )
                return {"_skipped": "kind_unknown_small_source"}

    if failure is not None:
        return {"_failure": failure}
    return success


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
        result = await compile_file(source, prefix=prefix, force=force_compile)
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
        from core.utils import append_history
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
