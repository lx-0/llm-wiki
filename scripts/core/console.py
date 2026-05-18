"""Shared console-logging setup for wiki CLI scripts.

Extracts the colored stderr formatter that originated in `compile.py`
(2026-05-15 UX upgrade) so every CLI command can have the same visual
language:

- INFO label hidden, WARNING/ERROR colored
- ``✓`` green, ``✗`` red wherever they appear in any message
- ``($X.XX)`` cost colorized by tier (dim < $0.05, plain, yellow ≥ $0.50,
  bold yellow ≥ $1.50)
- ``Ns`` elapsed and ``in:N out:N`` tokens dimmed
- ``─── … ───`` section banners bolded
- TTY-detected: ANSI sequences only when stderr is interactive (piped
  output stays clean)

Scripts emitting their own structural patterns (per-file headers,
dispatch lines, curiosity markers) subclass :class:`ConsoleFormatter`
and override :meth:`ConsoleFormatter._format_message_extras` to add a
script-specific colorization layer on top. Everything else just calls
:func:`setup_console_logging` and inherits the generic colors.

Architectural fit: this mirrors the engine's preference for pre-passes
in deterministic Python rather than per-script copy-paste — same shape
as ``core.compile_role.infer_compile_role`` and ``core.prompts.render``
which all started in one script and got hoisted when sibling scripts
grew the same need.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path


# ── ANSI color codes ───────────────────────────────────────────────────────
# Empty strings when stderr isn't a TTY so escape sequences don't leak
# into captured logs / CI output / piped reductions.

_TTY = sys.stderr.isatty()
C_RESET = "\033[0m" if _TTY else ""
C_DIM = "\033[2m" if _TTY else ""
C_BOLD = "\033[1m" if _TTY else ""
C_RED = "\033[31m" if _TTY else ""
C_GREEN = "\033[32m" if _TTY else ""
C_YELLOW = "\033[33m" if _TTY else ""
C_CYAN = "\033[36m" if _TTY else ""


def is_tty() -> bool:
    """Whether stderr is an interactive terminal at module-import time."""
    return _TTY


# ── Generic formatter ──────────────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s  %(levelname)s  %(message)s"
_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"


class ConsoleFormatter(logging.Formatter):
    """Generic colored stderr formatter; subclass to add CLI-specific lines.

    Subclasses override :meth:`_format_message_extras` to intercept lines
    matching their own regexes. Returning ``None`` falls through to the
    generic colorization (success/failure markers, cost tiers, elapsed,
    tokens, section banners).
    """

    # NOTE: colors looked up via _level_color() rather than a class-time
    # dict — the module-level C_* constants are captured at import time
    # based on stderr.isatty(), but tests monkeypatch them per-fixture.
    # Computing at format-time is the difference between a clean test
    # surface and a "frozen first import" footgun.

    # Matches `$X` or `$X.XX` anywhere in the message — whether wrapped in
    # parens like `($0.50)` (compile.py shape) or bare like `cap $5.00`
    # (dream.py shape). Each match gets tier-colored on its own; surrounding
    # parens, prefixes, suffixes stay plain so operators see the amount
    # highlighted without losing the surrounding context.
    _COST_RE = re.compile(r"\$(\d+(?:\.\d+)?)")
    _SECTION_RE = re.compile(r"^─── .+ ───$")
    _ELAPSED_RE = re.compile(r"\b(\d+\.\d+s)\b")
    _TOKENS_RE = re.compile(r"\b(in:[\w.,]+\s+out:[\w.,]+)")

    @staticmethod
    def _level_color(levelname: str) -> str:
        if levelname == "WARNING":
            return C_YELLOW
        if levelname == "ERROR":
            return C_RED
        if levelname == "CRITICAL":
            return C_RED + C_BOLD
        return ""

    def _colorize_cost(self, msg: str) -> str:
        def _sub(m: re.Match[str]) -> str:
            amount = float(m.group(1))
            if amount >= 1.50:
                color = C_BOLD + C_YELLOW
            elif amount >= 0.50:
                color = C_YELLOW
            elif amount < 0.05:
                color = C_DIM
            else:
                return m.group(0)
            return f"{color}${m.group(1)}{C_RESET}"
        return self._COST_RE.sub(_sub, msg)

    def _format_message_extras(self, msg: str) -> str | None:
        """Subclass hook for CLI-specific patterns.

        Return a fully-colorized replacement string when a subclass's
        regex matched, or ``None`` to fall through to the generic
        colorization layer below.
        """
        return None

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()

        if _TTY:
            # Subclass first crack — owns the line if its regex matched.
            override = self._format_message_extras(msg)
            if override is not None:
                msg = override
            elif self._SECTION_RE.match(msg.strip()):
                msg = f"{C_BOLD}{msg}{C_RESET}"
            else:
                # Generic colorization: markers, cost, elapsed, tokens.
                msg = msg.replace("✓", f"{C_GREEN}✓{C_RESET}")
                msg = msg.replace("✗", f"{C_RED}✗{C_RESET}")
                msg = self._colorize_cost(msg)
                msg = self._ELAPSED_RE.sub(f"{C_DIM}\\1{C_RESET}", msg)
                msg = self._TOKENS_RE.sub(f"{C_DIM}\\1{C_RESET}", msg)

        level_color = self._level_color(record.levelname)
        level_text = "" if record.levelname == "INFO" else record.levelname
        level = level_text.ljust(7)
        if level_color and _TTY and level_text:
            level = f"{level_color}{level_text}{C_RESET}".ljust(
                7 + len(level_color) + len(C_RESET)
            )

        return f"{C_DIM}{ts}{C_RESET}  {level}  {msg}"


# ── Noise filter ───────────────────────────────────────────────────────────


class SdkNoiseFilter(logging.Filter):
    """Drop high-volume SDK noise from console (file handlers keep it).

    The Claude Agent SDK prints ``Using bundled Claude Code CLI: <path>``
    once per ``query(...)`` call — at ~100 files/batch that's 100 useless
    full-path lines on stderr. File handlers don't carry this filter so
    the archive still has the lines for debugging.
    """

    _DROP_SUBSTRINGS = (
        "Using bundled Claude Code CLI:",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self._DROP_SUBSTRINGS)


# ── One-stop setup helper ──────────────────────────────────────────────────


def setup_console_logging(
    logger_name: str,
    *,
    formatter: ConsoleFormatter | None = None,
    log_file: Path | None = None,
    error_file: Path | None = None,
    silence_libraries: bool = True,
) -> logging.Logger:
    """One-stop logging setup for a CLI script.

    Replaces the boilerplate ``logging.basicConfig(...)`` + per-script
    handler glue with a single call that gives every CLI the same look.

    Args:
        logger_name: returned via ``logging.getLogger(...)`` for the
            caller's use (the named logger; root is configured behind
            the scenes with the console handler).
        formatter: a :class:`ConsoleFormatter` (or subclass) instance for
            stderr. ``None`` uses the base formatter (generic colors).
        log_file: optional ``Path`` for an INFO+ archive (verbose ISO
            timestamps, no colors).
        error_file: optional ``Path`` for a WARNING+ archive.
        silence_libraries: silence ``httpx``/``httpcore`` and the SDK's
            pre-exception ``"Fatal error in message reader"`` line so the
            caller's own classifier output is the first error visible.

    Returns:
        The named logger.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Idempotent stderr-handler setup. When a CLI module lazy-imports
    # another CLI module at run-time (incident 2026-05-18: dream.py
    # lazy-imported compile.py for `_build_owner_block`, triggering
    # compile's module-level setup_console_logging call and stacking a
    # second StreamHandler on root), every log line afterwards would
    # double-emit on stderr — once per formatter. Guard against this
    # by reusing any existing stderr StreamHandler (FIRST-call's
    # formatter wins; the importing CLI's style stays). File handlers
    # are deduped by path so the second module's compile.log handler
    # doesn't pile on either.
    have_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    )
    if not have_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter or ConsoleFormatter())
        console_handler.addFilter(SdkNoiseFilter())
        root.addHandler(console_handler)

    archive_fmt = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    existing_file_paths = {
        h.baseFilename for h in root.handlers if isinstance(h, logging.FileHandler)
    }
    if log_file is not None and str(log_file.resolve()) not in existing_file_paths:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(log_file, encoding="utf-8")
        h.setFormatter(archive_fmt)
        h.setLevel(logging.INFO)
        root.addHandler(h)

    if error_file is not None and str(error_file.resolve()) not in existing_file_paths:
        error_file.parent.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(error_file, encoding="utf-8")
        h.setFormatter(archive_fmt)
        h.setLevel(logging.WARNING)
        root.addHandler(h)

    if silence_libraries:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("claude_agent_sdk._internal.query").setLevel(logging.CRITICAL)

    return logging.getLogger(logger_name)
