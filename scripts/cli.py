"""Table-driven dispatcher for the `wiki` CLI — runs what the catalogue declares and
renders `wiki help` and the per-command help from it.

Why this module exists (architecture-deepening C06)
----------------------------------------------------
The `wiki` bash entry-point used to maintain the command catalog in four
hand-synced places (a header comment printed by `wiki help`, per-command
heredocs, each script's argparse, and `menu.py`'s hand-curated catalog). All
four drifted — `wiki help` was blind to 9 dispatcher-known commands. This
module inverts the ownership: the `CommandSpec` table (`cli_catalog.COMMANDS`)
is the catalog. `wiki help` renders from it (every command visible), the bash
layer is the bootstrap and delegates every command here (M034-S05-T03), and
`menu.py`'s coverage is pinned against the table by a test.

It also concentrates two policies the bash layer used to re-implement unsafely:

* Post-command dashboard refresh runs ONCE, through `flush.py`'s existing
  fcntl-locked implementation (imported, never reimplemented) — replacing eight
  copy-pasted, unlocked bash call sites that reopened the concurrent-regen
  window closed after the 2026-05-03 SessionEnd storm.
* OAuth bootstrap dispatches over an in-process registry with the account id
  passed as a function argument (`wiki auth <service> <account-id>`), replacing
  three `python -c` sites that interpolated operator-typed text into source.

Dispatch model
--------------
`main(argv)` looks up `argv[0]` in the table. A `py` command is run as a child
process (`sys.executable <script> <args…>`) — same isolation the old
`_run_script` bash helper gave, so a heavy script's asyncio loop / SDK state
never leaks into this dispatcher. `wiki help [<cmd>]` is answered here, every help
text through `cli_help.print_help` (M034-S05-T04). `auth` routes to the OAuth registry.

Layout (M033-S04-T07): the table, `BY_NAME` and the OAuth registry live in
`cli_catalog`, the per-command help texts in `cli_help`; this module keeps the
dispatch and the rendering, and re-exports the catalogue names consumers read as
`cli.X`. What the tests patch (`_run_child`, `refresh_dashboards`, `run_auth`)
stays here, where `run_command` / `main` read it.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from cli_catalog import _GROUP_ORDER, AUTH_SERVICES, BY_NAME, COMMANDS, CommandSpec, SubRoute
from cli_help import print_help
from core.console import print_error
from core.entry import child_env, python_m

SCRIPTS_DIR = Path(__file__).resolve().parent
WIKI_DIR = SCRIPTS_DIR.parent

# ── stdout styling ──────────────────────────────────────────────────────
# `wiki help` + command banners go to stdout, so TTY-detect on stdout (the
# core.console C_* constants gate on stderr and would be wrong here). Non-TTY
# callers (pipes, hooks, desktop capturing stdout) get plain text.
_STDOUT_TTY = sys.stdout.isatty()
_BOLD = "\033[1m" if _STDOUT_TTY else ""
_DIM = "\033[2m" if _STDOUT_TTY else ""
_CYAN = "\033[36m" if _STDOUT_TTY else ""
_RESET = "\033[0m" if _STDOUT_TTY else ""


def _err(msg: str) -> None:
    print_error(msg)


def _banner(title: str, subtitle: str | None = None) -> None:
    """The bash `banner` (lib/common.sh, gone in M034-S05-T05): bold title, optional dim subtitle, blank.

    Flush explicitly: when stdout is a pipe (desktop / hooks capture it) Python
    block-buffers, so without a flush the buffered banner would land AFTER the
    child process's output. bash's `printf` was unbuffered — preserve that."""
    print(f"{_BOLD}{title}{_RESET}")
    if subtitle:
        print(f"{_DIM}{subtitle}{_RESET}")
    print()
    sys.stdout.flush()


# ── OAuth registry ──────────────────────────────────────────────────────


def run_auth(rest: list[str]) -> int:
    """Dispatch `wiki auth <service> <account-id>` over AUTH_SERVICES."""
    if not rest or rest[0] in ("-h", "--help", "help"):
        _print_help_text(BY_NAME["auth"])
        return 0
    service = rest[0]
    if service not in AUTH_SERVICES:
        _err(f"unknown auth service: {service} (expected: {', '.join(AUTH_SERVICES)})")
        return 1
    # `wiki auth gmail` (no id) / `wiki gmail-auth` alias with no id -> service help.
    if len(rest) < 2 or rest[1] in ("-h", "--help", "help"):
        _print_help_text(BY_NAME["auth"])
        return 0
    account_id = rest[1]
    module_name, func_name = AUTH_SERVICES[service]
    module = importlib.import_module(module_name)
    bootstrap = getattr(module, func_name)
    ok, message = bootstrap(account_id)
    print(message)
    return 0 if ok else 1


# ── Dashboard refresh ───────────────────────────────────────────────────


def refresh_dashboards() -> None:
    """Refresh the vault Dashboard caches ONCE, via flush.py's existing
    fcntl-locked + timeout-guarded implementation.

    Importing flush is the sanctioned path (the lock was built there after the
    2026-05-03 SessionEnd storm and must not be duplicated). The import is
    lazy so commands that don't refresh — and `wiki help` — never pay for it.
    """
    import flush

    flush.refresh_dashboard_stats()
    flush.refresh_dashboard_lint()


# ── Help rendering ──────────────────────────────────────────────────────


def _print_help_text(command: CommandSpec) -> None:
    if command.help_text:
        print_help(command.help_text)
    else:
        print(f"{_BOLD}wiki {command.name}{_RESET} — {command.summary}")


def _help_for(name: str) -> int:
    """`wiki help <cmd>`: what `wiki <cmd> --help` prints; an alias answers with its
    target's. The catalogue alone used to print, and the name was dropped."""
    command = BY_NAME.get(name)
    if command is not None and command.kind == "alias":
        command = BY_NAME.get(command.alias_of[0])
    if command is None:
        _err(f"unknown command: {name} (try 'wiki help')")
        return 1
    _print_help_text(command)
    return 0


def render_help() -> str:
    """The full `wiki help` catalog, grouped, every command visible."""
    width = max(len(c.name) for c in COMMANDS) + 2
    lines: list[str] = [
        f"{_BOLD}{_CYAN}wiki{_RESET} — personal knowledge-base engine",
        "",
        f"{_DIM}usage: wiki <command> [args]   ·   wiki <command> --help for details{_RESET}",
        "",
    ]
    for group in _GROUP_ORDER:
        members = [c for c in COMMANDS if c.group == group]
        if not members:
            continue
        lines.append(f"{_BOLD}{group}{_RESET}")
        for c in members:
            lines.append(f"  {_CYAN}{c.name:<{width}}{_RESET}{c.summary}")
        lines.append("")
    lines.append(f"{_BOLD}DOCS{_RESET}")
    lines.append(f"  {WIKI_DIR / 'README.md'}")
    return "\n".join(lines)


# ── Command dispatch ────────────────────────────────────────────────────


def _run_child(script_rel: str, args: list[str]) -> int:
    """Run one handler as a child process — `python -m <module>` with `scripts/` first
    on the child's PYTHONPATH (`core.entry`; the same process isolation `_run_script`
    gave, and sub-package entry points need no `sys.path` bootstrap of their own). The
    working directory is inherited, so a relative argument (`wiki ingest-html ./page.html`)
    resolves against the operator's cwd. Returns the child's exit code."""
    completed = subprocess.run(python_m(script_rel, *args), env=child_env(), check=False)
    return completed.returncode


def _route(command: CommandSpec, rest: list[str]) -> tuple[SubRoute | None, list[str]]:
    """The route ``rest`` selects, and the argv left for it: a route the first argument
    names (its key consumed), else the default route when there is no argument or the first
    is a `--flag` (nothing consumed — `wiki dream --dry-run` is a sweep), else none."""
    if rest:
        named = next((s for s in command.subroutes if s.key == rest[0]), None)
        if named is not None:
            return named, rest[1:]
    if command.default_route and (not rest or rest[0].startswith("--")):
        return next(s for s in command.subroutes if s.key == command.default_route), rest
    return None, rest


def run_command(command: CommandSpec, rest: list[str]) -> int:
    """Dispatch a `py` command: help-intercept, banner, run, refresh-after."""
    # Top-level per-command help (deeper `wiki x sub -h` falls through to the
    # script's own argparse).
    if rest and rest[0] in ("-h", "--help", "help"):
        _print_help_text(command)
        return 0
    if not rest and command.show_help_on_empty:
        _print_help_text(command)
        return command.empty_help_exit

    script = command.handler
    banner_title = f"wiki {command.name}"
    subtitle = command.banner_subtitle
    banner_on = command.banner
    args = rest

    sub, remaining = _route(command, rest)
    if sub is not None:
        script = sub.script
        banner_title = sub.banner or banner_title
        subtitle = sub.subtitle
        banner_on = sub.banner is not None
        args = [*sub.args, *remaining]
    elif rest and not command.takes_args:
        _err(f"unknown: wiki {command.name} {rest[0]} (try 'wiki {command.name} help')")
        return 1
    else:
        args = [*command.handler_args, *rest]

    if script is None:
        # A command with no default handler (backfill) and no matching subroute.
        if not rest:
            _print_help_text(command)
            return 0
        _err(f"unknown: wiki {command.name} {rest[0]} (try 'wiki {command.name} help')")
        return 1

    # `--json` is a machine-readable seam (the desktop parses `wiki query --json`):
    # stdout is the payload alone, so no banner (`tests/test_bash_json_banner.py` holds it
    # end to end through `wiki`).
    if banner_on and "--json" not in args:
        _banner(banner_title, subtitle)
    code = _run_child(script, args)
    if command.refresh_after:
        refresh_dashboards()
    return code


def _interactive() -> bool:
    """Both ends a terminal — the bare-entry rule the bash `wiki` checked with `-t 0 && -t 1`."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def main(argv: list[str]) -> int:
    if not argv:
        # Bare `wiki`: the home screen for a person at a terminal; help for everyone else
        # (CI, pipes, hooks, cron), who must never block on a prompt.
        if _interactive():
            return run_command(BY_NAME["menu"], [])
        print(render_help())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("help", "-h", "--help"):
        if rest:
            return _help_for(rest[0])
        print(render_help())
        return 0
    if cmd == "refresh-dashboards":
        refresh_dashboards()
        return 0
    if cmd == "auth":
        return run_auth(rest)
    command = BY_NAME.get(cmd)
    if command is not None and command.kind == "alias":
        return main([*command.alias_of, *rest])
    if command is None or command.kind != "py":
        _err(f"unknown command: {cmd} (try 'wiki help')")
        return 1
    return run_command(command, rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
