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
import os
import re
import select
import sys
import termios
import time
import tty
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

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


def print_error(message: str) -> None:
    """A command's one-line error on stderr: a red ✗ on a terminal, `wiki: ` otherwise (the
    prefix scripts and the desktop grep for). The dispatcher and the commands ported from
    bash share it, so every `wiki` error reads the same (M034-S01-T05 / S02-T02)."""
    prefix = f"{C_RED}✗ {C_RESET}" if _TTY else "wiki: "
    print(f"{prefix}{message}", file=sys.stderr)


# ── stdout status lines ────────────────────────────────────────────────────
# The bash `ok` / `warn` / `info` / `banner`, which wrote to stdout, for the commands ported
# from it (M034). Styled by stdout's terminal state at call time — the bash's `[[ -t 1 ]]` —
# so a piped or captured run gets plain text.


def _styled(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def ok(message: str) -> None:
    print(_styled("32", f"✓ {message}"))


def warn(message: str) -> None:
    print(_styled("33", f"! {message}"))


def info(message: str) -> None:
    print(_styled("34", message))


def fail(message: str) -> None:
    """The bash `err`: a ✗ status line on stderr, red on a terminal. One failed item of a
    run, beside `ok`'s ✓ lines; a command's own one-line error is `print_error`."""
    line = f"✗ {message}"
    print(f"\033[31m{line}\033[0m" if sys.stderr.isatty() else line, file=sys.stderr)


def banner(title: str, subtitle: str | None = None) -> None:
    """A command's heading: bold title, dim subtitle, a blank line — flushed, so a child
    process started next writes below it."""
    print(_styled("1", title))
    if subtitle:
        print(_styled("2", subtitle))
    print()
    sys.stdout.flush()


# ── Single-keypress input ──────────────────────────────────────────────────
# Used by every interactive picker / prompt in the engine (home menu,
# curiosity walk, future review flows). cbreak mode + os.read(1) gives
# bulletproof single-byte input — no Enter required — and works wherever a
# POSIX terminal does. Shared here next to the C_* constants so input +
# output share one console-substrate module.


def read_key(fd: int | None = None) -> str:
    """Read one keypress from `fd` (default stdin) in cbreak mode.

    Returns:
        - ``'up'`` / ``'down'`` / ``'left'`` / ``'right'`` for arrow keys
        - ``'enter'`` for newline / carriage-return
        - ``'esc'`` for bare Escape
        - ``'c-c'`` / ``'c-d'`` for Ctrl-C / Ctrl-D
        - the literal character otherwise (e.g. ``'c'``, ``'3'``, ``'/'``).

    The terminal state is restored before return regardless of how the
    function exits — callers can safely wrap repeated calls in a loop.
    """
    if fd is None:
        fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = os.read(fd, 1)
        if not ch:
            return "c-d"
        b = ch[0]
        if b == 0x03:
            return "c-c"
        if b == 0x04:
            return "c-d"
        if b in (0x0A, 0x0D):
            return "enter"
        if b == 0x1B:
            # ESC — bare or arrow-sequence (ESC [ A/B/C/D). Give the
            # rest of the sequence ~50 ms to arrive before deciding.
            r, _, _ = select.select([fd], [], [], 0.05)
            if not r:
                return "esc"
            seq = os.read(fd, 2)
            if seq.startswith(b"[") and len(seq) >= 2:
                return {
                    b"A": "up",
                    b"B": "down",
                    b"C": "right",
                    b"D": "left",
                }.get(seq[1:2], "esc")
            return "esc"
        return ch.decode("utf-8", errors="replace")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Line-based prompts ─────────────────────────────────────────────────────
# The Python counterpart of lib/ui.sh (M034-S02-T01). Line-based like bash `read -r`: an
# answer piped on stdin is read, and EOF takes the default — how the bash oracle drives the
# interactive commands and how they behave without a terminal. Input is read byte by byte
# from the fd, never through `sys.stdin`: on a pipe `sys.stdin.readline()` buffers ahead
# and swallows the answers a child started after the prompt must read (`wiki setup` →
# `wiki hooks install`). Prompts go to stderr — stdout is the value, stderr the UX.
# questionary / prompt_toolkit were measured on a pipe and rejected (DECISIONS 2026-10-15):
# they warn, write a terminal redraw into stdout and consume all of the remaining stdin.

_NUMBER = re.compile(r"[0-9]+")


def read_line(fd: int = 0) -> str | None:
    """One line from ``fd`` without its newline, read a byte at a time so nothing past it is
    consumed. ``None`` at EOF with nothing read; a last line without a newline is returned."""
    buf = bytearray()
    while True:
        ch = os.read(fd, 1)
        if not ch or ch == b"\n":
            if not ch and not buf:
                return None
            return buf.decode("utf-8", errors="replace")
        buf += ch


def _emit(out: TextIO | None, text: str) -> None:
    stream = out if out is not None else sys.stderr
    if stream is not sys.stdout:
        # What was printed before a prompt shows before it, also when both streams go into
        # one pipe (`2>&1 | tee`): stdout is block-buffered there, the prompt's stream not.
        sys.stdout.flush()
    stream.write(text)
    stream.flush()


def confirm(prompt: str, default: bool = True, *, fd: int = 0, out: TextIO | None = None) -> bool:
    """``[Y/n]`` / ``[y/N]``. An empty line or EOF takes the default; a leading y or j
    (German "ja") is yes, anything else no."""
    _emit(out, f"{prompt} {'[Y/n]' if default else '[y/N]'} ")
    line = read_line(fd)
    if not line:
        return default
    return line[0] in "yYjJ"


def ask(
    prompt: str,
    default: str = "",
    validate: Callable[[str], bool] | None = None,
    *,
    fd: int = 0,
    out: TextIO | None = None,
) -> str:
    """A line, or the default for an empty one. A ``validate`` that returns False asks
    again — except at EOF, where no further answer will come: the default then, not a loop."""
    hint = f" {C_DIM}[{default}]{C_RESET}" if default else ""
    while True:
        _emit(out, f"{prompt}{hint}: ")
        line = read_line(fd)
        if line is None:
            return default
        value = line or default
        if validate is None or validate(value):
            return value


def _numbered(options: list[str], marked: Callable[[int, str], bool], out: TextIO | None) -> None:
    for i, option in enumerate(options, 1):
        marker = f"{C_GREEN}*{C_RESET} " if marked(i, option) else "  "
        _emit(out, f"  {marker}{i}) {option}\n")


def select_one(
    prompt: str,
    options: list[str],
    default: int = 1,
    *,
    fd: int = 0,
    out: TextIO | None = None,
) -> str:
    """One of ``options`` by its 1-based number; anything that is not a number in range —
    an empty line and EOF included — takes ``default``."""
    _numbered(options, lambda i, _option: i == default, out)
    _emit(out, f"{prompt} [{default}]: ")
    line = read_line(fd) or ""
    choice = int(line) if _NUMBER.fullmatch(line) else default
    if not 1 <= choice <= len(options):
        choice = default
    return options[choice - 1]


def select_many(
    prompt: str,
    options: list[str],
    defaults: list[str],
    *,
    fd: int = 0,
    out: TextIO | None = None,
) -> list[str]:
    """Space-separated 1-based numbers; an empty line or EOF takes ``defaults``. Tokens that
    are not a number in range are skipped."""
    _numbered(options, lambda _i, option: option in defaults, out)
    hint = f"{C_DIM} (space-separated numbers, Enter for defaults marked *){C_RESET}"
    _emit(out, f"{prompt}{hint}: ")
    line = read_line(fd)
    if not line:
        return list(defaults)
    return [
        options[int(token) - 1]
        for token in line.split()
        if _NUMBER.fullmatch(token) and 1 <= int(token) <= len(options)
    ]


def pause(text: str = "Press Enter to continue", *, fd: int = 0, out: TextIO | None = None) -> None:
    """Wait for one line (or EOF)."""
    _emit(out, f"{C_DIM}{text}{C_RESET} ")
    read_line(fd)


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
            level = f"{level_color}{level_text}{C_RESET}".ljust(7 + len(level_color) + len(C_RESET))

        return f"{C_DIM}{ts}{C_RESET}  {level}  {msg}"


# ── Noise filter ───────────────────────────────────────────────────────────


class SdkNoiseFilter(logging.Filter):
    """Drop high-volume SDK noise from console (file handlers keep it).

    The Claude Agent SDK prints ``Using bundled Claude Code CLI: <path>``
    once per ``query(...)`` call — at ~100 files/batch that's 100 useless
    full-path lines on stderr. File handlers don't carry this filter so
    the archive still has the lines for debugging.
    """

    _DROP_SUBSTRINGS = ("Using bundled Claude Code CLI:",)

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
    level: int = logging.INFO,
    silence_libraries: bool = True,
) -> logging.Logger:
    """One-stop logging setup for a CLI script — the engine's one logging setup.

    Replaces the boilerplate ``logging.basicConfig(...)`` + per-script
    handler glue with a single call that gives every CLI the same look.
    Called from the entry point (``main()`` / the ``__main__`` block), never
    at module level: an importable module must not configure its importer's
    root logger (KNOWLEDGE "no basicConfig in importable modules").

    Args:
        logger_name: returned via ``logging.getLogger(...)`` for the
            caller's use (the named logger; root is configured behind
            the scenes with the console handler).
        formatter: a :class:`ConsoleFormatter` (or subclass) instance for
            stderr. ``None`` uses the base formatter (generic colors).
        log_file: optional ``Path`` for an INFO+ archive (verbose ISO
            timestamps, no colors).
        error_file: optional ``Path`` for a WARNING+ archive.
        level: the root level (default INFO; the home-screen probe runs at
            WARNING so its INFO never reaches the operator's terminal).
        silence_libraries: silence ``httpx``/``httpcore`` and the SDK's
            pre-exception ``"Fatal error in message reader"`` line so the
            caller's own classifier output is the first error visible.

    Returns:
        The named logger.
    """
    root = logging.getLogger()
    root.setLevel(level)

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
