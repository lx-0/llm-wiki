"""One output path (M034 exit criterion 5): a command's output goes through `core.console`.

The command modules — every handler and subroute script the catalogue dispatches, `cli.py`
for the commands it answers itself (help, auth, refresh-dashboards, the banner), and every
collector module `wiki collect` runs (its Registry run, or its own CLI after `--`) — write
through `say` and the status helpers (`ok` / `warn` / `info` / `fail` / `print_error` /
`banner`), never through a `print(` of their own. The gate below walks their syntax trees,
so a docstring that names print is not a call and a new call fails with its module and line.
Before the conversion: 391 calls in 36 of the 47 modules (M034-S06-T02), 24 in three
collector modules (S06-T04), and 7 in `cli.py` (S06-T06).
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path

import cli_catalog
import collectors
from core import console

SCRIPTS = Path(cli_catalog.__file__).resolve().parent

# A command module that may still call print, with the reason. Empty: none needs to.
ALLOWED: dict[str, str] = {}


def _command_modules() -> list[str]:
    # cli.py answers the builtin and auth commands itself (`wiki help`, `wiki auth …`,
    # `wiki refresh-dashboards`) and prints every command's banner (M034-S06-T06).
    scripts = {"cli.py"} | {c.handler for c in cli_catalog.COMMANDS if c.handler}
    scripts |= {s.script for c in cli_catalog.COMMANDS for s in c.subroutes}
    scripts |= {f"{m.replace('.', '/')}.py" for m in collectors.MODULES.values()}
    return sorted(scripts)


def test_no_command_module_calls_print():
    calls = [
        f"{module}:{node.lineno}"
        for module in _command_modules()
        if module not in ALLOWED
        for node in ast.walk(ast.parse((SCRIPTS / module).read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert calls == [], f"{len(calls)} print( call(s) outside core.console:\n" + "\n".join(calls)


def test_every_allowed_module_says_why():
    assert all(reason.strip() for reason in ALLOWED.values())
    assert set(ALLOWED) <= set(_command_modules()), "an allowlist entry names no command module"


def test_say_writes_to_the_stream_of_the_moment(monkeypatch, capsys):
    """Stdout unless told otherwise, judged at call time — a test's capture or a caller's
    swapped stream sees the line, as with print."""
    console.say("a", 1, sep="-")
    console.say("no newline", end="")
    assert capsys.readouterr().out == "a-1\nno newline"

    swapped = io.StringIO()
    monkeypatch.setattr(sys, "stderr", swapped)
    console.say("to stderr", file=sys.stderr)
    assert swapped.getvalue() == "to stderr\n"
