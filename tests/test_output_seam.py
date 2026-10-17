"""One output path (M034 exit criterion 5): a command's output goes through `core.console`.

The command modules write through `say` and the status helpers (`ok` / `warn` / `info` /
`fail` / `print_error` / `banner`), never through a `print(` of their own. They are the
entry points — every handler and subroute script the catalogue dispatches, `cli.py` for the
commands it answers itself, every collector module `wiki collect` runs — AND every
`scripts/` module those import or spawn by path, directly or through others: a shim's logic
prints as much as the shim, a spawned child's output is the command's output.
`core/console.py` is the seam itself. The gate walks their syntax trees, so a docstring
that names print is not a call and a new call fails with its module and line.
Before the conversion: 391 calls in 36 of the 47 entry modules (M034-S06-T02), 24 in three
collector modules (S06-T04), 7 in `cli.py` (S06-T06), and 44 in nine modules behind the
entry points — `process-inbox`'s and `ingest-html`'s preprocessors, `wiki study`'s runner,
`wiki config`'s `core.config._cli`, the help seam, the agent buttons, publish's OAuth, and
the two dashboard generators `wiki refresh-dashboards --dry-run` spawns (S06-T07: the
entry-only gate had missed them).
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

# A command module that may still call print, with the reason.
ALLOWED: dict[str, str] = {
    "core/contracts.py": (
        "`python -m core.contracts --write/--check`, the contributors' schema generator that "
        "the suite runs; no wiki command calls its main"
    ),
}


def _entry_modules() -> set[str]:
    # cli.py answers the builtin and auth commands itself (`wiki help`, `wiki auth …`,
    # `wiki refresh-dashboards`) and prints every command's banner (M034-S06-T06).
    scripts = {"cli.py"} | {c.handler for c in cli_catalog.COMMANDS if c.handler}
    scripts |= {s.script for c in cli_catalog.COMMANDS for s in c.subroutes}
    scripts |= {f"{m.replace('.', '/')}.py" for m in collectors.MODULES.values()}
    return scripts


def _module_file(dotted: str) -> str | None:
    base = SCRIPTS.joinpath(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate.relative_to(SCRIPTS).as_posix()
    return None


def _reached(module: str) -> set[str]:
    """The `scripts/` modules ``module`` imports (absolute and relative forms) or spawns by
    path — a string that names a script, as `python_m("compile.py")`, a handler constant
    (`DASHBOARD_STATS_HANDLER`) or a piggyback's task row passes it."""
    package = module.split("/")[:-1]
    names: set[str] = set()
    spawned: set[str] = set()
    for node in ast.walk(ast.parse((SCRIPTS / module).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            stem = node.module or ""
            if node.level:
                parent = package[: len(package) - (node.level - 1)]
                stem = ".".join([*parent, stem]) if stem else ".".join(parent)
            names.add(stem)
            names.update(f"{stem}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.endswith(".py") and (SCRIPTS / node.value).is_file():
                spawned.add(node.value)
    return spawned | {f for name in names if (f := _module_file(name)) is not None}


def _command_modules() -> list[str]:
    seen: set[str] = set()
    queue = sorted(_entry_modules())
    while queue:
        module = queue.pop()
        if module in seen or not (SCRIPTS / module).is_file():
            continue
        seen.add(module)
        queue.extend(_reached(module) - seen)
    seen.discard("core/console.py")  # the seam itself
    return sorted(seen)


def test_the_gate_follows_imports_past_the_entry_points():
    """`process-inbox` enters through a shim whose logic lives in a preprocessor."""
    modules = _command_modules()
    assert "process_inbox.py" in modules
    assert "preprocessors/inbox.py" in modules
    assert "core/console.py" not in modules


def test_the_gate_follows_children_spawned_by_path():
    """`wiki refresh-dashboards --dry-run` prints what the two generators print — `cli.py`
    spawns them by the path constants in `flush.py`, it never imports them."""
    modules = _command_modules()
    assert "dashboard/dashboard_stats.py" in modules
    assert "dashboard/dashboard_lint.py" in modules


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
