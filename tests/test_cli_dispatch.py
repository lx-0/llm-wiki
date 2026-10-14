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


@pytest.mark.parametrize(
    ("handler", "module"),
    [
        ("compile.py", "compile"),
        ("review_wiki.py", "review_wiki"),
        ("preprocessors/inbox.py", "preprocessors.inbox"),
        ("preprocessors/html_ingest.py", "preprocessors.html_ingest"),
        ("collectors/cli.py", "collectors.cli"),
        ("facts/correct.py", "facts.correct"),
    ],
)
def test_handler_path_maps_to_module(handler: str, module: str) -> None:
    assert cli.module_for(handler) == module


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


@pytest.mark.parametrize("entry", ["process_inbox", "ingest_html"])
def test_preprocessor_entry_modules_run_once_without_runpy_warning(entry: str) -> None:
    """`preprocessors/__init__.py` imports `inbox` and `html_ingest` to register them, so
    `python -m preprocessors.inbox` would execute the module twice and runpy warns
    ("found in sys.modules after import of package"). The top-level entry modules exist
    to avoid exactly that — this is the guard."""
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
