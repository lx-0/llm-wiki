"""`cli.py` spawns handlers as modules (`python -m <module>`) with `scripts/` on the
child's PYTHONPATH — so sub-package entry points (`preprocessors.inbox`,
`collectors.cli`, …) need no `sys.path` bootstrap of their own, and the caller's
working directory is inherited (relative arguments such as `ingest-html ./page.html`
keep resolving against the operator's cwd). M033-S02 (layout decision: `scripts/` is
the source root)."""

from __future__ import annotations

import os
import sys

import pytest

import cli


def test_run_child_spawns_module_with_scripts_on_pythonpath(monkeypatch, tmp_path) -> None:
    seen: dict = {}

    class _Done:
        returncode = 7

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return _Done()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setenv("PYTHONPATH", "/somewhere/else")
    monkeypatch.chdir(tmp_path)

    rc = cli._run_child("preprocessors/inbox.py", ["--dry-run", "./page.html"])

    assert rc == 7
    assert seen["cmd"] == [sys.executable, "-m", "preprocessors.inbox", "--dry-run", "./page.html"]
    env = seen["kwargs"]["env"]
    first, *rest = env["PYTHONPATH"].split(os.pathsep)
    assert first == str(cli.SCRIPTS_DIR), "scripts/ must come first so core.* resolves"
    assert "/somewhere/else" in rest, "the caller's PYTHONPATH is kept, not replaced"
    assert "cwd" not in seen["kwargs"], "cwd is inherited so relative arguments keep working"
    assert seen["kwargs"]["check"] is False


@pytest.mark.parametrize(
    "entry",
    [
        "process_inbox",
        "ingest_html",
        "ingest_youtube",
        "index_folders",
    ],
)
def test_entry_modules_run_once_without_runpy_warning(entry: str) -> None:
    """`preprocessors/__init__.py` imports its modules to register them, so
    `python -m preprocessors.inbox` would execute the module twice and runpy warns ("found in
    sys.modules after import of package"). The top-level entry modules exist to avoid that —
    this is the guard. `wiki index` and `wiki ingest-youtube` printed that warning on every
    real run after T03 moved the spawns to `-m`; `--help` never showed it because cli.py
    answers `--help` itself (M033-S02-T05). The `collectors` package imports no collector
    since M034-S06-T03; its two entries stay the commands' entry points, and the three
    by-path collector scripts went with `wiki collect <name> -- <flags>` (S06-T04)."""
    import subprocess

    env = dict(os.environ, PYTHONPATH=str(cli.SCRIPTS_DIR))
    proc = subprocess.run(
        [sys.executable, "-m", entry, "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RuntimeWarning" not in proc.stderr
    assert "found in sys.modules" not in proc.stderr


def test_no_handler_lives_in_a_package_that_imports_it() -> None:
    """A handler under a package whose `__init__` imports that module runs twice under
    `python -m` (runpy's double import, see the test above). Such a command needs a
    top-level entry module — this catches the next handler that reaches into a registry
    package directly."""
    offenders: list[str] = []
    for spec in cli.COMMANDS:
        if not spec.handler or "/" not in spec.handler:
            continue
        pkg, _, rest = spec.handler.partition("/")
        mod = rest.removesuffix(".py").replace("/", ".")
        init = cli.SCRIPTS_DIR / pkg / "__init__.py"
        if not init.exists():
            continue
        text = init.read_text(encoding="utf-8")
        if f"from {pkg} import {mod}\n" in text or f"from {pkg}.{mod} import" in text:
            offenders.append(f"{spec.name} → {spec.handler}")
    assert offenders == [], (
        "handlers that would double-import under -m (give them a top-level entry module):\n"
        + "\n".join(offenders)
    )
