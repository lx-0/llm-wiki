"""Interactive home screen for the `wiki` CLI.

Replaces the bash home_screen + category browse + fuzzy filter that
landed in commits 6504ab6 → acae830 → 1852029. The bash version hit
a chain of bash-3.2 quirks (fractional read -t, empty array under
set -u, missing ${var,,}) that each cost a commit; prompt_toolkit
handles all of it natively.

Invoked by the bash entry-point on bare `wiki` (TTY) or `wiki menu`.
Dispatches every action by shelling out to `wiki <subcommand>` —
never re-implements cmd_*. The bash dispatcher is the single source
of truth for what each subcommand does.

Cold-start: import prompt_toolkit is deferred until after the probe
runs (~80ms saved before any rendering work begins). Subsequent
loop iterations reuse the already-imported module.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.health import CheckResult, build_health
from core.paths import ROOT_DIR, WIKI_DIR
from menu_context import build_status, build_suggestions

WIKI_BIN = WIKI_DIR / "wiki"


# ── Static dispatch catalog ─────────────────────────────────────────
#
# Each entry: (id, label, description, dispatch).
# `dispatch` is either:
#   list[str]                 — pass straight to `wiki <args>`
#   ("prompt", label, args)   — ask for one arg, substitute {arg} in args
#   ("special", name)         — invoke a builtin handler (e.g. fuzzy filter)
#
# The shape is reused by:
#   - QUICK_ACTIONS  (4 entries, single-letter shortcuts)
#   - CATEGORIES     (6 buckets × 4-11 entries, browse sub-menus)
#   - FUZZY_CATALOG  (~49 entries, `/foo` substring filter)
# Hand-curated; the list churns slowly.


QUICK_ACTIONS: list[tuple[str, str, str, object]] = [
    ("q", "query",  "ask the wiki ($$)",            ("special", "query")),
    ("f", "flush",  "capture current session",      ["flush"]),
    ("l", "lint",   "cheap structural lint",        ["lint", "--structural-only"]),
    ("s", "status", "config + hooks + ollama",      ["status"]),
]


CATEGORIES: dict[str, tuple[str, list[tuple[str, str, str, object]]]] = {
    "c": ("collectors", [
        ("list",          "list collectors",                "see what's registered",                  ["collect", "--list"]),
        ("run",           "run a collector",                "by name (see 'list' first)",             ("prompt", "Collector name", ["collect", "{arg}"])),
        ("gmail",         "gmail OAuth bootstrap",          "one-time per account",                   ("prompt", "Account id",     ["gmail-auth", "{arg}"])),
        ("gmeet",         "gmeet OAuth bootstrap",          "Google Meet transcripts",                ("prompt", "Account id",     ["gmeet-auth", "{arg}"])),
        ("calendar",      "calendar OAuth bootstrap",       "Google Calendar events",                 ("prompt", "Account id",     ["calendar-auth", "{arg}"])),
    ]),
    "i": ("ingest", [
        ("inbox",         "process inbox/ folder",          "classify + route via Ollama",            ["process-inbox"]),
        ("html",          "ingest one URL or HTML file",    "html2text → raw/articles",               ("prompt", "URL or path",            ["ingest-html", "{arg}"])),
        ("youtube",       "ingest YouTube",                 "video or playlist",                      ("prompt", "Video or playlist URL", ["ingest-youtube", "--url", "{arg}"])),
    ]),
    "k": ("knowledge ops", [
        ("compile",       "compile changed sources ($$)",   "incremental run",                        ["compile"]),
        ("compile-file",  "compile one file ($$)",          "vault-relative path",                    ("prompt", "Path", ["compile", "--file", "{arg}"])),
        ("lint-struct",   "lint (structural only)",         "no LLM, cheap",                          ["lint", "--structural-only"]),
        ("lint-full",     "lint (full, costs $)",           "incl. contradiction check",              ["lint"]),
        ("query",         "query the wiki ($$)",            "natural-language",                       ("special", "query")),
        ("review",        "review-wiki (local LLM, free)",  "per-article quality",                    ["review-wiki"]),
        ("dream-all",     "dream — sweep all entities ($$$)", "rewrite every entity page",            ["dream", "--all-entities"]),
        ("dream-one",     "dream — one entity ($$)",        "by slug",                                ("prompt", "Entity slug", ["dream-entity", "{arg}"])),
        ("pin",           "pin article to a MOC",           "by name or path",                        ("prompt", "Article", ["pin", "{arg}"])),
    ]),
    "d": ("facts/takes", [
        ("correct-list",  "list hard facts",                "knowledge/facts/*.md",                   ["correct", "list"]),
        ("correct-add",   "add a hard fact",                "title + truth",                          ("special", "correct_add")),
        ("correct-edit",  "edit a hard fact",               "open in $EDITOR",                        ("prompt", "Slug", ["correct", "edit", "{arg}"])),
        ("correct-remove","remove a hard fact",             "creates .bak",                           ("prompt", "Slug", ["correct", "remove", "{arg}"])),
        ("correct-apply", "propagate a hard fact ($$$)",    "agentic over vault",                     ("prompt", "Slug", ["correct", "apply", "{arg}"])),
        ("take-list",     "list takes",                     "knowledge/takes/*.md",                   ["take", "list"]),
        ("take-show",     "show takes for one holder",      "by slug",                                ("prompt", "Holder slug", ["take", "show", "{arg}"])),
    ]),
    "a": ("automation", [
        ("curio-list",    "curiosity — list requests",      "raw/requests/*.json",                    ["curiosity", "--list"]),
        ("curio-oldest",  "curiosity — run oldest",         "local LLM (free)",                       ["curiosity", "--run-oldest"]),
        ("curio-all",     "curiosity — run all",            "all pending",                            ["curiosity", "--run-all"]),
        ("curio-clear",   "curiosity — clear done",         "delete done files",                      ["curiosity", "--clear-done"]),
        ("sugg-list",     "suggestions — list",             "raw/suggestions/*.yaml",                 ["suggestions", "--list"]),
        ("sugg-review",   "suggestions — review one",       "interactive",                            ("prompt", "Suggestion id", ["suggestions", "--review", "{arg}"])),
        ("sugg-exec",     "suggestions — execute approved", "imap moves / tags",                      ["suggestions"]),
        ("flush",         "flush session now",              "manual override",                        ["flush"]),
        ("agent-list",    "list agent tasks",               "prompts/agents/*.md",                    ["agent", "--list"]),
        ("agent-run",     "run an agent task",              "by id",                                  ("prompt", "Task id", ["agent", "{arg}"])),
    ]),
    "g": ("setup", [
        ("status",        "status",                         "config + hooks + ollama",                ["status"]),
        ("wizard",        "run setup wizard",               "5 questions + hooks",                    ["setup"]),
        ("config",        "edit config interactively",      "lib/config.sh",                          ["config"]),
        ("hooks-status",  "hooks install table",            "per agent + scope",                      ["hooks", "status"]),
        ("hooks-install", "install hooks",                  "interactive picker",                     ["hooks", "install"]),
        ("skills-status", "skills install table",           "per skill + global",                     ["skills", "status"]),
        ("update",        "git pull + sync skills",         "ff-only",                                ["update"]),
        ("seed-audit",    "seed — audit drift",             "read-only",                              ["seed", "--check"]),
        ("seed-apply",    "seed — apply missing templates", "additive",                               ["seed"]),
        ("version",       "engine git revision",            "rev + origin",                           ["version"]),
    ]),
}


def _flatten_for_fuzzy() -> list[tuple[str, str, object]]:
    """All catalog entries as (id, description, dispatch) for the fuzzy filter."""
    out: list[tuple[str, str, object]] = []
    for letter, (_label, entries) in CATEGORIES.items():
        for eid, label, desc, dispatch in entries:
            out.append((f"{letter}-{eid}", f"{label} — {desc}", dispatch))
    for key, label, desc, dispatch in QUICK_ACTIONS:
        out.append((f"quick-{key}", f"{label} — {desc}", dispatch))
    return out


# ── Helpers ─────────────────────────────────────────────────────────


def render_status_line(status: dict) -> str:
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
    return subprocess.run([str(WIKI_BIN), *args]).returncode


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
    "query":       _handle_query,
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
        pick = pt.prompt(
            "Mode [d=default / b=brief / f=file-back] (default d): "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "default"
    return {"b": "brief", "f": "file-back"}.get(pick, "default")


# ── Home screen ─────────────────────────────────────────────────────


class HomeState:
    def __init__(self):
        self.status: dict = {}
        self.suggestions: list[dict] = []
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
        return [
            r for r in self.health
            if r.severity in ("critical", "warning") and r.dispatch_args
        ]

    def info_health(self) -> list[CheckResult]:
        """Health entries severity critical|warning WITHOUT dispatch_args.
        Rendered as a read-only Heads-up section below the actionable list
        — operator runs the fix manually (e.g. `tail …`, `claude /login`)."""
        return [
            r for r in self.health
            if r.severity in ("critical", "warning") and not r.dispatch_args
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
        items: list[dict] = []
        for r in self.actionable_health():
            items.append({
                "kind": "health",
                "severity": r.severity,
                "label": r.message,
                "dispatch_args": list(r.dispatch_args),
                "cmd_display": " ".join(r.dispatch_args),
            })
        for s in self.suggestions:
            cmd_str = s.get("cmd", "")
            items.append({
                "kind": "suggestion",
                "severity": "probe",
                "label": s.get("label", ""),
                "dispatch_args": cmd_str.split(),
                "cmd_display": cmd_str,
            })
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
        for i, act in enumerate(actions):
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
        lines.append(
            "  <ansibrightblack>✨ Nothing pending — vault is current.</ansibrightblack>"
        )
        lines.append("")

    # ── Heads-up: warnings without auto-fix ─────────────────────────
    # Critical/warning health entries that DON'T have a `dispatch_args`
    # (multi-step fix, shell-only, external — e.g. tail log, claude
    # /login, manual ollama check). Read-only — operator runs them.
    info_issues = state.info_health()
    if info_issues:
        lines.append(
            "  <b>▸ Heads-up</b>  "
            "<ansibrightblack>(read-only — fix manually)</ansibrightblack>"
        )
        for r in info_issues:
            if r.severity == "critical":
                glyph = "<ansired>✗</ansired>"
            else:
                glyph = "<ansiyellow>⚠</ansiyellow>"
            lines.append(f"      {glyph} {escape(r.message)}")
            if r.fix:
                lines.append(
                    f"        <ansibrightblack>→ {escape(r.fix)}</ansibrightblack>"
                )
        lines.append(
            "      <ansibrightblack>(`wiki doctor` for the full audit)</ansibrightblack>"
        )
        lines.append("")

    lines.append("  <b>▸ Quick actions</b>")
    lines.append(
        "      [<b>q</b>] query     [<b>f</b>] flush     "
        "[<b>l</b>] lint     [<b>s</b>] status"
    )
    lines.append("")

    lines.append("  <b>▸ Browse</b>")
    lines.append(
        "      [<b>c</b>] collectors    [<b>i</b>] ingest    "
        "[<b>k</b>] knowledge ops"
    )
    lines.append(
        "      [<b>d</b>] facts/takes   [<b>a</b>] automation "
        "[<b>g</b>] setup"
    )
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


def _run_home_picker(state: HomeState) -> None:
    """Single iteration of the home screen. Sets state.selected via key
    bindings, then exits the app."""
    pt = _import_pt()

    kb = pt.KeyBindings()

    @kb.add("up")
    def _(event):
        if state.cursor > 0:
            state.cursor -= 1

    @kb.add("down")
    def _(event):
        if state.cursor < state.n_actions() - 1:
            state.cursor += 1

    @kb.add("enter")
    def _(event):
        if 0 <= state.cursor < state.n_actions():
            state.selected = ("action", state.cursor)
            event.app.exit()

    @kb.add("/")
    def _(event):
        state.selected = ("filter",)
        event.app.exit()

    for q in ("q", "f", "l", "s"):
        @kb.add(q)
        def _(event, q=q):
            state.selected = ("quick", q)
            event.app.exit()

    for c in ("c", "i", "k", "d", "a", "g"):
        @kb.add(c)
        def _(event, c=c):
            state.selected = ("category", c)
            event.app.exit()

    @kb.add("h")
    def _(event):
        state.selected = ("help",)
        event.app.exit()

    @kb.add("x")
    def _(event):
        state.selected = ("exit",)
        event.app.exit()

    @kb.add("c-c")
    @kb.add("c-d")
    def _(event):
        state.selected = ("exit",)
        event.app.exit()

    for digit in "123456789":
        @kb.add(digit)
        def _(event, d=digit):
            idx = int(d) - 1
            if 0 <= idx < state.n_actions():
                state.selected = ("action", idx)
                event.app.exit()

    body = pt.Window(
        content=pt.FormattedTextControl(
            text=lambda: pt.HTML(_build_screen_html(state)),
            focusable=True,
        ),
        wrap_lines=False,
    )
    app = pt.Application(
        layout=pt.Layout(pt.HSplit([body])),
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    state.selected = None
    app.run()


def _open_category(letter: str) -> None:
    label, entries = CATEGORIES[letter]
    pt = _import_pt()
    print(f"\n  ▸ {label}\n")
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
        (id_, label, dispatch)
        for id_, label, dispatch in _flatten_for_fuzzy()
        if q in id_.lower()
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
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        # Non-TTY callers — defer to `wiki help`. Same posture as the
        # bash entry-point's TTY check.
        subprocess.run([str(WIKI_BIN), "help"])
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
                subprocess.run([str(WIKI_BIN), "help"])
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
    try:
        input("\nPress Enter to continue ")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    sys.exit(main())
