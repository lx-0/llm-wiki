"""Interactive home screen for the `wiki` CLI.

Replaces the bash home_screen + category browse + fuzzy filter that
landed in commits 6504ab6 → acae830 → 1852029. The bash version hit
a chain of bash-3.2 quirks (fractional read -t, empty array under
set -u, missing ${var,,}) that each cost a commit; prompt_toolkit
handles all of it natively.

Opened by cli.py on bare `wiki` at a terminal, or by `wiki menu`.
Dispatches every action by spawning `wiki <subcommand>` — never
re-implements a command. What it offers comes from the command
catalogue (`cli_catalog`: each command's `menu_items`), the same table
`wiki help` renders; the pending-work rows come from `core/actions`.

Cold-start: import prompt_toolkit is deferred until after the probe
runs (~80ms saved before any rendering work begins). Subsequent
loop iterations reuse the already-imported module.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable

from cli import render_help
from cli_catalog import COMMANDS, MENU_GROUPS, QUICK_KEYS, CommandSpec, MenuItem
from core.console import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    ConsoleFormatter,
    is_tty,
    read_key,
    setup_console_logging,
)
from core.contracts import StatusJSON, SuggestionJSON
from core.health import CheckResult, build_health
from core.paths import ROOT_DIR, WIKI_DIR
from menu_context import build_status, build_suggestions


class _MenuFormatter(ConsoleFormatter):
    """No timestamp + no level prefix. The screen render is the entire
    output line; the timestamp/level columns that compile uses would
    just produce visual noise around what is already a full TUI frame.

    Inherits from ConsoleFormatter so the menu uses literally the same
    formatter class as compile.py — guaranteed identical color-emit path
    end-to-end through Python's logging.StreamHandler."""

    def format(self, record):
        return record.getMessage()


_log = logging.getLogger("menu")

WIKI_BIN = WIKI_DIR / "wiki"


# ── Dispatch catalog, derived from cli_catalog ──────────────────────
#
# Each entry: (id, label, description, dispatch).
# `dispatch` is either:
#   list[str]                 — pass straight to `wiki <args>`
#   ("prompt", label, args)   — ask for one arg, substitute {arg} in args
#   ("special", name)         — invoke a builtin handler (e.g. fuzzy filter)
#
# The shape is reused by:
#   - QUICK_ACTIONS  (single-letter shortcuts, `MenuItem.quick`, in `QUICK_KEYS` order)
#   - CATEGORIES     (one per catalogue group with menu items, keyed by `MENU_GROUPS`)
#   - the fuzzy filter (every entry once, `/foo` substring filter)
# One table (M034-S06-T01): the entries live on the catalogue commands they run, so an
# entry cannot name a command `wiki` does not know, and `wiki help` and this menu share one
# taxonomy.


def _dispatch(command: CommandSpec, item: MenuItem) -> object:
    if item.special:
        return ("special", item.special)
    argv = [command.name, *item.args]
    return ("prompt", item.prompt, argv) if item.prompt else argv


def _derive_categories() -> dict[str, tuple[str, list[tuple[str, str, str, object]]]]:
    categories: dict[str, tuple[str, list[tuple[str, str, str, object]]]] = {}
    for group, letter in MENU_GROUPS:
        entries = [
            (item.key, item.label, item.hint, _dispatch(command, item))
            for command in COMMANDS
            if command.group == group
            for item in command.menu_items
        ]
        if entries:
            categories[letter] = (group, entries)
    return categories


def _derive_quick_actions() -> list[tuple[str, str, str, object]]:
    quick = {
        item.quick[0]: (item.quick[0], item.quick[1], item.label, _dispatch(command, item))
        for command in COMMANDS
        for item in command.menu_items
        if item.quick
    }
    return [quick[key] for key in QUICK_KEYS]


CATEGORIES = _derive_categories()
QUICK_ACTIONS = _derive_quick_actions()
_CATEGORY_KEYS: frozenset[str] = frozenset(CATEGORIES)


def _category_title(group: str) -> str:
    """A group as the browse row names it: the help's group, in the TUI's lower case."""
    return group.lower()


# Single source of truth for which single-key quick actions are live. Both the
# home-screen render (the footer under "Quick actions") and the key handler in
# `_run_home_picker` derive from this — so a QUICK_ACTIONS entry can never again
# be declared-but-unbound-and-unrendered (the dead 't' triage shortcut before
# C06). The every-key-bound-and-rendered contract is pinned by tests/test_menu.py.
_QUICK_KEYS: frozenset[str] = frozenset(key for key, *_ in QUICK_ACTIONS)


def _flatten_for_fuzzy() -> list[tuple[str, str, object]]:
    """All catalog entries as (id, description, dispatch) for the fuzzy filter — each once:
    a shortcut is a category entry with a key, not a row of its own."""
    return [
        (f"{letter}-{eid}", f"{label} — {desc}", dispatch)
        for letter, (_group, entries) in CATEGORIES.items()
        for eid, label, desc, dispatch in entries
    ]


# ── Helpers ─────────────────────────────────────────────────────────


def render_status_line(status: StatusJSON) -> str:
    parts: list[str] = []
    n = status.get("articles")
    if n is not None:
        parts.append(f"{n} article" + ("" if n == 1 else "s"))
    if status.get("last_compile_ago"):
        parts.append(f"last compile {status['last_compile_ago']} ago")
    if "ollama_reachable" in status:
        marker = "✓" if status["ollama_reachable"] else "✗"
        parts.append(f"ollama {marker}")
    return " · ".join(parts)


def dispatch_subprocess(args: list[str]) -> int:
    """Run `wiki <args>` with inherited stdio so the operator sees output."""
    if not WIKI_BIN.exists():
        print(f"wiki binary not found at {WIKI_BIN}", file=sys.stderr)
        return 1
    return subprocess.run([str(WIKI_BIN), *args], check=False).returncode


def render_dispatch(dispatch: object, arg_prompt: Callable[[str], str | None]) -> None:
    """Run a catalog entry's dispatch spec. arg_prompt is the callback the
    UI provides to read a single arg when the spec needs one."""
    if isinstance(dispatch, list):
        dispatch_subprocess(dispatch)
        return
    if isinstance(dispatch, tuple):
        kind = dispatch[0]
        if kind == "prompt":
            _, label, args = dispatch
            arg = arg_prompt(label)
            if not arg:
                return
            filled = [a.replace("{arg}", arg) for a in args]
            dispatch_subprocess(filled)
            return
        if kind == "special":
            name = dispatch[1]
            _SPECIAL_HANDLERS[name](arg_prompt)
            return
    print(f"unknown dispatch spec: {dispatch!r}", file=sys.stderr)


def _handle_query(arg_prompt: Callable[[str], str | None]) -> None:
    q = arg_prompt("Question")
    if not q:
        return
    # Three modes: default ($$), brief (cheaper), file-back (persisted).
    mode = _pick_query_mode()
    args = ["query", q]
    if mode == "brief":
        args.append("--brief")
    elif mode == "file-back":
        args.append("--file-back")
    dispatch_subprocess(args)


def _handle_correct_add(arg_prompt: Callable[[str], str | None]) -> None:
    title = arg_prompt("Title (one sentence)")
    if not title:
        return
    truth = arg_prompt("Truth (one sentence)")
    if not truth:
        return
    dispatch_subprocess(["correct", "add", title, truth])


_SPECIAL_HANDLERS: dict[str, Callable[[Callable[[str], str | None]], None]] = {
    "query": _handle_query,
    "correct_add": _handle_correct_add,
}


# ── prompt_toolkit (lazy) ───────────────────────────────────────────


def _import_pt():
    """Lazy import of prompt_toolkit primitives. Returns a module-like ns."""
    from prompt_toolkit import Application
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.shortcuts import prompt as pt_prompt

    class _PT:
        pass

    pt = _PT()
    pt.Application = Application
    pt.HTML = HTML
    pt.KeyBindings = KeyBindings
    pt.Layout = Layout
    pt.HSplit = HSplit
    pt.Window = Window
    pt.FormattedTextControl = FormattedTextControl
    pt.prompt = pt_prompt
    return pt


def _pt_ask(label: str, default: str = "") -> str | None:
    """Single-line prompt via prompt_toolkit. Returns None on Ctrl-C."""
    pt = _import_pt()
    try:
        return pt.prompt(f"{label}: ", default=default).strip() or None
    except (EOFError, KeyboardInterrupt):
        return None


def _pick_query_mode() -> str:
    """Tiny picker for query mode. Returns 'default' / 'brief' / 'file-back'."""
    pt = _import_pt()
    try:
        pick = pt.prompt("Mode [d=default / b=brief / f=file-back] (default d): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "default"
    return {"b": "brief", "f": "file-back"}.get(pick, "default")


# ── Home screen ─────────────────────────────────────────────────────

# Intent-classes for the actionable list (lever 2). The operator's confusion was
# "what must I do vs what's automatic"; grouping answers it at a glance.
_GROUP_RANK = {"do": 0, "auto": 1, "review": 2}
_GROUP_HEADERS = {
    "do": "Needs you",
    "auto": "Running automatically",
    "review": "Optional review",
}


class HomeState:
    def __init__(self):
        self.status: StatusJSON = {}
        self.suggestions: list[SuggestionJSON] = []
        self.health: list[CheckResult] = []
        self.cursor: int = 0
        self.selected: tuple | None = None
        # selected is one of:
        #   ("action", index)   — unified actionable list (health + suggestions)
        #   ("quick", key)
        #   ("category", letter)
        #   ("filter",)
        #   ("help",)
        #   ("exit",)

    def actionable_health(self) -> list[CheckResult]:
        """Health entries severity critical|warning with a dispatch_args.
        These are the ones the cursor can run via Enter."""
        return [r for r in self.health if r.severity in ("critical", "warning") and r.dispatch_args]

    def info_health(self) -> list[CheckResult]:
        """Health entries severity critical|warning WITHOUT dispatch_args.
        Rendered as a read-only Heads-up section below the actionable list
        — operator runs the fix manually (e.g. `tail …`, `claude /login`)."""
        return [
            r for r in self.health if r.severity in ("critical", "warning") and not r.dispatch_args
        ]

    def actions(self) -> list[dict]:
        """Unified actionable list: actionable-health first, then probe
        suggestions. Each entry is a dict with stable keys so the renderer
        + key handlers don't need isinstance() dispatch.

        Shape:
            {
              "kind": "health" | "suggestion",
              "severity": "critical" | "warning" | "probe",
              "label": str,           # human-readable
              "dispatch_args": list[str],  # passed to `wiki <args>`
              "cmd_display": str,     # what to render after "→ wiki "
            }
        """
        _SEV_RANK = {"critical": 0, "warning": 1}
        items: list[dict] = []
        for r in self.actionable_health():
            items.append(
                {
                    "kind": "health",
                    "severity": r.severity,
                    # Actionable health always needs the operator → `do` group.
                    "group": "do",
                    "label": r.message,
                    "dispatch_args": list(r.dispatch_args),
                    "cmd_display": " ".join(r.dispatch_args),
                    # Sort within a group: health (0) before suggestions (1), then
                    # by severity / priority.
                    "_sort": (0, _SEV_RANK.get(r.severity, 9)),
                }
            )
        for s in self.suggestions:
            argv = list(s.get("argv", []))
            items.append(
                {
                    "kind": "suggestion",
                    "severity": "probe",
                    "group": s.get("group", "do"),
                    "label": s.get("label", ""),
                    "dispatch_args": argv,
                    "cmd_display": " ".join(argv),
                    "_sort": (1, s.get("priority", 99)),
                }
            )
        # Group by intent-class (do → auto → review), preserving in-group order.
        items.sort(key=lambda it: (_GROUP_RANK.get(it["group"], 0), it["_sort"]))
        return items

    def n_actions(self) -> int:
        return len(self.actions())


def _build_screen_html(state: HomeState) -> str:
    from html import escape

    revision = _git_revision()
    vault_name = ROOT_DIR.name
    status_line = render_status_line(state.status) or "(no status fields)"

    lines: list[str] = [
        "",
        f"  <b><ansicyan>wiki</ansicyan></b> — {escape(vault_name)} vault (commit {escape(revision)})",
        f"  <ansibrightblack>{escape(status_line)}</ansibrightblack>",
        "",
    ]

    # ── Unified actionable list ─────────────────────────────────────
    # Health issues with `dispatch_args` set + every probe suggestion,
    # in priority order (health first by severity). Cursor + Enter +
    # 1-9 all index into this single list.
    actions = state.actions()
    if actions:
        lines.append(
            "  <b>▸ Actionable in your vault</b>  "
            "<ansibrightblack>(↑↓ Enter · 1-9 jump)</ansibrightblack>"
        )
        current_group: str | None = None
        for i, act in enumerate(actions):
            # Emit a group sub-header when the intent-class changes. Numbering
            # stays continuous 1..N across groups so 1-9 jumps still index
            # `actions()` directly.
            group = act.get("group", "do")
            if group != current_group:
                current_group = group
                header = _GROUP_HEADERS.get(group, group)
                lines.append(f"    <ansibrightblack>{escape(header)}</ansibrightblack>")
            sev = act["severity"]
            label = escape(act["label"])
            cmd_display = escape(act["cmd_display"])
            # Severity glyph in the gutter — colored health icon for
            # promoted health checks, blank space for probe suggestions
            # (their "actionable" status is implied by being in the list).
            if sev == "critical":
                gutter_glyph = "<ansired>✗</ansired>"
            elif sev == "warning":
                gutter_glyph = "<ansiyellow>⚠</ansiyellow>"
            else:
                gutter_glyph = " "
            # Cursor marker
            cursor_mark = "<ansigreen>▸</ansigreen>" if i == state.cursor else " "
            # Position number (1-9 keyboard shortcut)
            num = i + 1
            num_html = f"<ansigreen>{num})</ansigreen>" if num <= 9 else f"{num})"
            lines.append(
                f"   {cursor_mark} {gutter_glyph} {num_html} {label:<43}"
                f"  <ansibrightblack>→ wiki {cmd_display}</ansibrightblack>"
            )
        lines.append("")
    else:
        lines.append("  <ansibrightblack>✨ Nothing pending — vault is current.</ansibrightblack>")
        lines.append("")

    # ── Heads-up: warnings without auto-fix ─────────────────────────
    # Critical/warning health entries that DON'T have a `dispatch_args`
    # (multi-step fix, shell-only, external — e.g. tail log, claude
    # /login, manual ollama check). Read-only — operator runs them.
    info_issues = state.info_health()
    if info_issues:
        lines.append(
            "  <b>▸ Heads-up</b>  <ansibrightblack>(read-only — fix manually)</ansibrightblack>"
        )
        for r in info_issues:
            if r.severity == "critical":
                glyph = "<ansired>✗</ansired>"
            else:
                glyph = "<ansiyellow>⚠</ansiyellow>"
            lines.append(f"      {glyph} {escape(r.message)}")
            if r.fix:
                lines.append(f"        <ansibrightblack>→ {escape(r.fix)}</ansibrightblack>")
        lines.append("      <ansibrightblack>(`wiki doctor` for the full audit)</ansibrightblack>")
        lines.append("")

    lines.append("  <b>▸ Quick actions</b>")
    # Derived from QUICK_ACTIONS so every declared shortcut is rendered — no
    # hand-synced footer that can drift out of sync with the key handler.
    quick = "  ".join(
        f"[<b>{escape(key)}</b>] {escape(label)}" for key, label, _desc, _disp in QUICK_ACTIONS
    )
    lines.append(f"      {quick}")
    lines.append("")

    lines.append("  <b>▸ Browse</b>")
    # Derived from CATEGORIES (the catalogue's groups), three to a row.
    browse = [
        f"[<b>{escape(letter)}</b>] {escape(_category_title(group))}"
        for letter, (group, _entries) in CATEGORIES.items()
    ]
    for row in range(0, len(browse), 3):
        lines.append("      " + "   ".join(browse[row : row + 3]))
    lines.append("")
    lines.append(
        "      [<b>h</b>] full help     [<b>x</b>] exit     "
        "<ansibrightblack>(type <b>/foo</b> to filter all commands)</ansibrightblack>"
    )
    lines.append("")
    lines.append(
        "  <ansibrightblack>↑↓ Enter · 1-9 · letter · / for filter · Ctrl-C to exit</ansibrightblack>"
    )

    return "\n".join(lines)


def _git_revision() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(WIKI_DIR), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


# ── Raw-mode single-key home picker ─────────────────────────────────
#
# prompt_toolkit's Application setup (full_screen=False + FormattedTextControl)
# turned out to be fragile in operator terminals — single keypresses got
# line-buffered (had to press Enter) and ANSI HTML didn't always render
# colors. Both symptoms point at pt's input/output autodetection mis-firing
# in real iTerm2 sessions despite the right TERM. The home picker is small
# enough to own directly: termios+tty.setcbreak gives bulletproof single-key
# input, and ANSI escape sequences guarantee colors in any vt100-compatible
# terminal (which iTerm2/Terminal.app/VS Code-terminal all are).
#
# prompt_toolkit stays for line-input subprompts (_pt_ask, _pick_query_mode)
# where its history + editing pay off; the home loop owns its own input.

# Tag→ANSI table sourced from `core.console`'s C_* constants — exactly the
# same byte sequences compile.py / dream.py emit, all
# gated by the same `is_tty()` (stderr.isatty()) flag. If compile's colors
# render in the operator's terminal, the menu's render too — they are now
# literally the same bytes on the same stream.
_ANSI_TAGS = {
    "<b>": C_BOLD,
    "</b>": C_RESET,
    "<ansicyan>": C_CYAN,
    "</ansicyan>": C_RESET,
    "<ansired>": C_RED,
    "</ansired>": C_RESET,
    "<ansigreen>": C_GREEN,
    "</ansigreen>": C_RESET,
    "<ansiyellow>": C_YELLOW,
    "</ansiyellow>": C_RESET,
    "<ansibrightblack>": C_DIM,
    "</ansibrightblack>": C_RESET,
}
_TAG_RE = re.compile("|".join(re.escape(k) for k in _ANSI_TAGS))


def _html_to_ansi(s: str) -> str:
    """Convert the prompt_toolkit HTML subset used by _build_screen_html
    into raw ANSI. Also un-escapes the three named entities html.escape()
    can produce (`&amp;`, `&lt;`, `&gt;`)."""
    out = _TAG_RE.sub(lambda m: _ANSI_TAGS[m.group(0)], s)
    return out.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _run_home_picker(state: HomeState) -> None:
    """Single iteration of the home screen. Sets state.selected then returns.

    Renders directly to stdout with ANSI; reads keys with termios in cbreak
    mode (one byte at a time). Single key fires immediately — no Enter."""
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        state.selected = ("exit",)
        return

    state.selected = None
    # Track height of previous render so we can step the cursor back over
    # it on redraw (compile never clears the screen — same convention here).
    prev_lines = 0
    while state.selected is None:
        screen = _html_to_ansi(_build_screen_html(state))
        # Cursor-up + erase prefix lives on the same logged record as the
        # screen body so they reach the terminal via one StreamHandler
        # write — identical emit path to compile.py's per-line log records.
        # Empty separator string here so logging.StreamHandler appends only
        # ONE terminator at the end of the whole frame.
        prefix = f"\x1b[{prev_lines}F\x1b[J" if (prev_lines and is_tty()) else ""
        _log.info("%s%s", prefix, screen)
        prev_lines = screen.count("\n") + 1

        try:
            key = read_key(fd)
        except (KeyboardInterrupt, OSError):
            state.selected = ("exit",)
            return

        if key in ("c-c", "c-d", "esc"):
            state.selected = ("exit",)
            return
        if key == "up":
            if state.cursor > 0:
                state.cursor -= 1
            continue
        if key == "down":
            if state.cursor < state.n_actions() - 1:
                state.cursor += 1
            continue
        if key == "enter":
            if 0 <= state.cursor < state.n_actions():
                state.selected = ("action", state.cursor)
            continue
        if key == "/":
            state.selected = ("filter",)
            continue
        if key in _QUICK_KEYS:
            state.selected = ("quick", key)
            continue
        if key in _CATEGORY_KEYS:
            state.selected = ("category", key)
            continue
        if key == "h":
            state.selected = ("help",)
            continue
        if key == "x":
            state.selected = ("exit",)
            continue
        if key in "123456789":
            idx = int(key) - 1
            if 0 <= idx < state.n_actions():
                state.selected = ("action", idx)
            continue
        # Unbound key — silently redraw.


def _open_category(letter: str) -> None:
    group, entries = CATEGORIES[letter]
    pt = _import_pt()
    print(f"\n  ▸ {_category_title(group)}\n")
    for i, (_eid, item_label, desc, _disp) in enumerate(entries, start=1):
        print(f"    {i:>2}) {item_label:<32} {desc}")
    print()
    try:
        pick = pt.prompt(f"Pick (1-{len(entries)}, Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not pick:
        return
    if not pick.isdigit() or not (1 <= int(pick) <= len(entries)):
        print(f"  invalid: {pick!r}")
        return
    _eid, _label, _desc, dispatch = entries[int(pick) - 1]
    render_dispatch(dispatch, _pt_ask)


def _fuzzy_filter(query: str) -> None:
    """`/foo` typed at home — substring-match against the catalog."""
    q = query.lower().strip()
    if not q:
        print("  (empty query)")
        return
    matches = [
        (id_, label, dispatch) for id_, label, dispatch in _flatten_for_fuzzy() if q in id_.lower()
    ]
    if not matches:
        print(f"  no command matches '/{query}'")
        return
    if len(matches) == 1:
        id_, label, dispatch = matches[0]
        print(f"  one match: {id_} — {label}")
        render_dispatch(dispatch, _pt_ask)
        return
    print(f"\n  Matches for /{query}:\n")
    for i, (id_, label, _disp) in enumerate(matches, start=1):
        print(f"    {i:>2}) {id_:<22}  {label}")
    print()
    pt = _import_pt()
    try:
        pick = pt.prompt(f"Pick (1-{len(matches)}, Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not pick:
        return
    if not pick.isdigit() or not (1 <= int(pick) <= len(matches)):
        print(f"  invalid: {pick!r}")
        return
    _id, _label, dispatch = matches[int(pick) - 1]
    render_dispatch(dispatch, _pt_ask)


# ── Main loop ───────────────────────────────────────────────────────


def main() -> int:
    # The screen render is one log record per frame (`_log.info` in the loop): the
    # menu formatter goes on root here, at the entry point, never at import.
    setup_console_logging("menu", formatter=_MenuFormatter())
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        # Non-TTY callers get `wiki help`, rendered here rather than spawned through the
        # entry again (bash → python → python; M034-S06-T01). Same posture as bare `wiki`.
        print(render_help())
        return 0

    state = HomeState()
    try:
        while True:
            state.status = build_status()
            state.suggestions = build_suggestions()
            state.health = build_health()
            n = state.n_actions()
            if n == 0:
                state.cursor = 0  # safe even when there's nothing to highlight
            elif state.cursor >= n:
                state.cursor = n - 1

            _run_home_picker(state)

            if state.selected is None:
                # App exited without a selection (rare; treat as exit).
                return 0

            tag = state.selected[0]
            if tag == "exit":
                return 0
            if tag == "action":
                idx = state.selected[1]
                actions = state.actions()
                if 0 <= idx < len(actions):
                    print()
                    dispatch_subprocess(actions[idx]["dispatch_args"])
                    _pause()
            elif tag == "quick":
                key = state.selected[1]
                spec = next(d for k, _l, _d, d in QUICK_ACTIONS if k == key)
                print()
                render_dispatch(spec, _pt_ask)
                _pause()
            elif tag == "category":
                _open_category(state.selected[1])
                _pause()
            elif tag == "help":
                print()
                print(render_help())
                _pause()
            elif tag == "filter":
                pt = _import_pt()
                try:
                    sub = pt.prompt("/").strip()
                except (EOFError, KeyboardInterrupt):
                    sub = ""
                _fuzzy_filter(sub)
                _pause()
    except KeyboardInterrupt:
        return 0


def _pause() -> None:
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input("\nPress Enter to continue ")


if __name__ == "__main__":
    sys.exit(main())
