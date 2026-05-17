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
      - curiosity line  `  Curiosity*`                  dim cyan + `?` prefix
                                                        (info, not action; magenta
                                                        read as error in dark terminals)
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
            # Curiosity engine lines — dim cyan + `?` glyph prefix.
            # Curiosity is informational (the gap-detection loop wrote N
            # requests for the next compile to pick up); it's NOT a
            # compile failure. Earlier magenta choice read as red/error
            # in dark terminals and competed with the actual red ✗
            # failure marker. Dim cyan parks the lines in the ambient-
            # log register (same weight as dispatch / elapsed / tokens);
            # the `?` glyph signals "inquiry", matching the loop's name.
            elif self._CURIOSITY_RE.match(msg):
                marked = re.sub(r"^(\s+)Curiosity", r"\1? Curiosity", msg, count=1)
                msg = f"{_C_DIM}{_C_CYAN}{marked}{_C_RESET}"
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

from compile_stages.post_passes import run_post_passes  # noqa: E402


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

# Substrate-aware prompt dispatch.
#
# Maps frontmatter `type:` value to (prompt_name, max_turns, model_override).
# Default fall-through (for ANY substrate-type not listed here) is
# `_DEFAULT_DISPATCH` which routes to `compile_default.md` on Haiku
# at a tight 12-turn budget. This is the "safe-by-default" posture:
# new substrate types that nobody has profiled yet cost pennies, not
# dollars. compile_main.md is the heavy dialog-substrate carry-forward
# prompt and is EXPLICIT-ONLY — add an entry below to route a type to
# it (e.g. for jamie/gmeet transcripts that legitimately need
# State+Timeline rewrites + Action Item routing).
#
# Empirical history (2026-05-16): five substrate types hit max_turns
# at $2-5/file when they implicitly fell through to compile_main —
# calendar-rollup, daily-digest, health-rollup, screenshot-batch,
# memory-sync. Each got a dedicated lean prompt and Haiku routing.
# That whack-a-mole pattern is what motivates the safe-by-default
# fallback: future unknown types route to compile_default first; if
# they need richer treatment, profile them and add an explicit entry.
#
# SubstrateProfile: (prompt_name, max_turns, model_override or None).
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
    "screenshot-batch": ("compile_screenshots", 30, "claude-haiku-4-5-20251001"),
    # Camera/phone-photo batches (collectors/pictures.py). Picture-shaped
    # fields (scene_description / objects / action / text_visible) and a
    # much tighter anti-noise filter — most camera photos become zero
    # knowledge entries. 20 turns + Haiku covers the rare actionable
    # batch (whiteboard captures, receipts, document scans).
    "picture-batch":    ("compile_pictures", 20, "claude-haiku-4-5-20251001"),
    # Memory-sync = cross-project AGENTS/CLAUDE.md copies. Memory-seed =
    # aggregated per-project memory dumps, split per-section by classify.py.
    # Either way: ONE excerpt per compile call. The rewritten compile_memories.md
    # (2026-05-17) is a tight 3-step contract — Glob → Read → Edit-append
    # Timeline — with a hard 5-turn budget in-prompt. 8 here is the CLI-level
    # safety cap (~60% over budget); the prompt's anti-loop branch emits
    # `{"status": "no_project_page"}` before reaching the CLI cap.
    # Previously 25 turns: Haiku ignored the prompt's anti-loop guard and
    # burned $0.35 per chunk hitting max_turns. See KNOWLEDGE.md and
    # commits f289a43 (circuit-breaker) + this commit (prompt rewrite).
    "memory-sync":     ("compile_memories", 8, "claude-haiku-4-5-20251001"),
    "memory-seed":     ("compile_memories", 8, "claude-haiku-4-5-20251001"),
}

# Default for any substrate-type NOT in SUBSTRATE_PROMPTS. Lean prompt
# + Haiku + operator-tunable budget. The max_turns is read from CONFIG
# at module-import time so a vault-side bump to
# `limits.compile_max_turns` actually changes the fall-through routing —
# the previous hardcoded `12` made the config knob dead code (operator
# couldn't tune the default via config; only by editing this module).
_DEFAULT_DISPATCH: tuple[str, int, str | None] = (
    "compile_default", CONFIG.limits.compile_max_turns, "claude-haiku-4-5-20251001",
)


# Path-prefix → substrate_key fallback for legacy substrate files that
# don't carry the new `type:` frontmatter yet. Producers SHOULD emit a
# frontmatter type going forward (so SUBSTRATE_PROMPTS lookup hits the
# direct path), but until every existing vault file is backfilled the
# path-pattern fallback keeps compile-dispatch sane. Pattern: matched
# against the source path with `startswith`. Longer-prefix wins on
# overlap; iterate from most-specific to least-specific.
_SUBSTRATE_PATH_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("raw/notes/screenshots/screenshots-", "screenshot-batch"),
    ("raw/notes/pictures/pictures-",       "picture-batch"),
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


def _frontmatter_compile_role(content: str) -> str | None:
    """Extract `compile_role:` from leading YAML frontmatter, or None.

    Sibling to `_frontmatter_type`; same regex-only rationale. Returns the
    raw string value — caller passes it to `core.compile_role.infer_compile_role`
    for enum validation and default-by-location inference (M007-S02-T01).
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    m = re.search(r"^compile_role:\s*[\"']?([\w-]+)[\"']?\s*$", block, re.MULTILINE)
    return m.group(1) if m else None


def _frontmatter_field(content: str, key: str) -> str | None:
    """Extract a scalar frontmatter field value by key, or None.

    Generic sibling to `_frontmatter_type`. Tolerates quoted values (`"`, `'`)
    and trailing whitespace; matches first occurrence of `<key>:` inside the
    leading `---` fence. Designed for title-like scalars — does NOT parse
    nested structures or lists (use yaml.safe_load for those).
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    # Allow any non-newline chars in the value (spaces, punctuation, etc.)
    pattern = rf"^{re.escape(key)}:\s*[\"']?(.*?)[\"']?\s*$"
    m = re.search(pattern, block, re.MULTILINE)
    return m.group(1).strip() if m else None


def _build_owner_block() -> str:
    """Render the operator/vault-owner context block for substrate compile prompts.

    Returns "" when `personal.implicit_operator_author` is unset (multi-tenant
    vaults) — prompts that interpolate `${owner_block}` simply emit no
    section. When set, returns a self-contained "## Operator / vault owner"
    Markdown block with the operator's name, a pointer to
    `knowledge/people/<slug>.md`, and a Read-on-demand hint. The page
    contents are NOT embedded — keeps the block small (~400 chars) so
    substrate prompts stay budget-safe; the agent Reads the page when it
    needs more context (self-reference resolution, connection targets).
    """
    owner = (CONFIG.personal.implicit_operator_author or "").strip()
    if not owner:
        return ""
    page_rel = f"knowledge/people/{owner}.md"
    page_abs = KNOWLEDGE_DIR / "people" / f"{owner}.md"
    if page_abs.exists():
        existence = f"see `{page_rel}`"
    else:
        existence = (
            f"`{page_rel}` does not yet exist — create it via the stub-rules "
            "in §6 when substrate first introduces this person"
        )
    return (
        "## Operator / vault owner\n\n"
        f"This vault belongs to **{owner}** — {existence}.\n\n"
        "When distilling first-person beliefs, commitments, or decisions from "
        f"a source that has no explicit `author:` frontmatter, attribute them "
        f"to **{owner}**. You MAY Read `{page_rel}` to resolve self-references "
        "(\"I\", \"we\", \"my company\") and to find existing entries you "
        "should connect new facts to.\n"
    )


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

    # compile_role dispatch (M007-S02-T01). The frontmatter axis decides how
    # this file participates in compile:
    #   - source-only       → distill into knowledge/ (today's behavior)
    #   - source-and-final  → indexed-only; the page IS the final form (T02
    #                         implements the real index-only branch; today
    #                         it falls through to source-only distillation)
    #   - final-only        → engine-skip; hand-curated; reachable via
    #                         grep/graph/search but hidden from MOC + dashboard
    # Inference (when frontmatter omits `compile_role:`) uses LOCATION_DEFAULTS
    # from `core.compile_role` and is gated by
    # `CONFIG.limits.compile_role_default_by_location` (M007-S01-T02 knob).
    explicit_role = _frontmatter_compile_role(source_content)
    fm_for_role = {"compile_role": explicit_role} if explicit_role else {}
    from core.compile_role import infer_compile_role
    compile_role = infer_compile_role(
        source, fm_for_role,
        default_by_location=CONFIG.limits.compile_role_default_by_location,
        vault_root=ROOT_DIR,
    )
    if compile_role == "final-only":
        log.warning(
            "  skipping: compile_role=final-only (hand-curated, engine-skip)",
        )
        return {"_skipped": "compile_role_final_only"}
    if compile_role == "source-and-final":
        # The page IS the final form. Index-only: extract wikilinks for
        # discoverability, append a knowledge/index.md entry by pathname,
        # NO SDK distill call, NO separate knowledge/concepts/<title>.md.
        # (M007-S02-T02. Connections-build deferred — Obsidian Graph
        # picks up the wikilinks natively in the meantime.)
        from core.utils import build_index_entry, extract_wikilinks
        wikilinks = extract_wikilinks(source_content)
        log.info(
            "  source-and-final: indexing only (no distill) — %d wikilinks discovered",
            len(wikilinks),
        )
        title = (
            _frontmatter_field(source_content, "title")
            or source.stem.replace("-", " ").replace("_", " ").title()
        )
        new_entry = build_index_entry(
            rel_path, title, "(source-and-final)", today_iso(),
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
        # Mark as ingested with its hash so `check_orphan_sources` lint doesn't
        # flag this file (it IS the final form — not "uncompiled substrate") and
        # re-runs of compile become true no-ops via the hash-skip in select_files.
        # (M007-S02-T04. Mirrors the post-distill state update at line ~1130.)
        state = load_state()
        if "ingested" not in state:
            state["ingested"] = {}
        state["ingested"][rel_path] = file_hash(source)
        save_state(state)
        return {"_skipped": "compile_role_source_and_final_indexed"}
    # source-only falls through to current distill behavior (unchanged).

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
        dispatch_key or "", _DEFAULT_DISPATCH,
    )
    # Log the dispatch decision when it's an explicit SUBSTRATE_PROMPTS
    # match (interesting routing) — skip the noise of "type=X → default"
    # for the safe-by-default fallback.
    if dispatch_key in SUBSTRATE_PROMPTS:
        # Truncate model id for readability: "claude-haiku-4-5-20251001"
        # → "haiku-4-5". Keep the full id in the underlying records.
        short_model = ""
        if substrate_model:
            m = re.match(r"claude-(haiku|sonnet|opus)-(\d+-\d+)", substrate_model)
            short_model = f" @ {m.group(1)}-{m.group(2)}" if m else f" @ {substrate_model}"
        log.info("  type=%s → %s%s", source_type, substrate_prompt, short_model)

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

    # Pre-compile classifier (compile_stages.classify) decides whether the
    # substrate shape needs special handling BEFORE the LLM call:
    #   - aggregated-memory  -> split-at-H2 in memory, compile per-chunk
    #     (raw file untouched). Fixes the cross-link fanout that blows the
    #     25-turn budget on substrates carrying N memories.
    #   - instructions       -> AGENTS.md/CLAUDE.md/README.md accidentally
    #     ingested into raw/memories/. Routed to compile_instructions.md
    #     for single-pass project-doc handling, no fanout.
    #   - single             -> unchanged single compile call.
    # raw/ is RAW: chunking rebuilds substrate strings in memory only.
    from compile_stages.classify import classify
    classification = classify(source_content, source)

    if classification.kind == "instructions":
        substrate_prompt = "compile_instructions"
        max_turns_for_call = max(max_turns_for_call, 20)
        log.info(
            "  classified as instructions-doc -> routing to %s @ %d turns",
            substrate_prompt, max_turns_for_call,
        )

    from compile_stages.compile import compile_source
    from compile_stages.types import CompileMetadata
    metadata = CompileMetadata(
        source_path=source,
        compile_role=compile_role,
        model_id=model,
        max_turns=max_turns_for_call,
        substrate_type=source_type,
        substrate_prompt=substrate_prompt,
    )

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
            return {
                "_skipped": "aggregated_memory_circuit_breaker"
                if aborted_at is not None
                else "aggregated_memory_all_chunks_failed"
            }
        return {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": total_cost,
            "result": (
                f"aggregated-memory: {ok_count}/{len(classification.chunks)} "
                f"chunks compiled"
                + (f" (aborted at {aborted_at})" if aborted_at is not None else "")
            ),
        }

    result = await compile_source(source_content, metadata)

    if result.status == "skipped":
        # Map compile_source's skip_reason to the legacy compile_file _skipped
        # tags. The two values differ only for the long-context kind=unknown
        # case — the rest are identical strings.
        legacy_reason = {
            "long_context_kind_unknown": "kind_unknown_on_long_context",
        }.get(result.skip_reason or "", result.skip_reason or "unknown")
        return {"_skipped": legacy_reason}

    if result.status == "failed":
        return {"_failure": FailureClass(
            result.failure_kind or "unknown",
            result.failure_detail or "(see logs)",
        )}

    return {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "result": result.article or "",
    }




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

        prefix = f"[{idx}/{cap}] "
        result = await compile_file(source, prefix=prefix, force=force_compile)
        if result is not None and "_skipped" in result:
            # Skipped (empty file, dry-run, substrate-type skip-list): neither
            # success nor failure. Don't touch the failure-streak counter — it
            # tracks real failures for abort thresholds. Count separately for
            # the summary so "pending" doesn't lie when the operator's
            # skip-list quietly drained the batch.
            skipped_count += 1
            # source-and-final files mutate state["ingested"] from inside
            # compile_file (M007-S02-T04). The local `state` here is stale
            # vs. disk after that mutation — reload so subsequent per-file
            # saves at lines 1232-1237 + final save at 1241-1243 don't
            # clobber the source-and-final ingest entry.
            if result["_skipped"] == "compile_role_source_and_final_indexed":
                state = load_state()
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

        # Post-pass producers (Producer-seam arc, .ytstack/backlog/producer-seam.md).
        # `run_post_passes` iterates every registered Producer serially (Q1
        # decision), absorbs per-producer raises into `ProducerResult(status="failed")`
        # via the orchestrator's contract-α wrapper, and accumulates
        # `cost_usd` into `state["producer_cost_total"]` so the save below
        # persists it alongside total_cost / last_compile.
        from compile_stages.types import CompileResult
        _compile_result = CompileResult(
            status="ok",
            cost_usd=result.get("cost_usd", 0.0),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            article=result.get("result"),
        )
        await run_post_passes(source, _compile_result, state)

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


if __name__ == "__main__":
    asyncio.run(main())
