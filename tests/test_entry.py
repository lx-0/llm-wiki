"""`core.entry` — the one place that knows how an engine module is spawned.

`scripts/` is the engine's source root (DECISIONS 2026-10-14): a child runs as
`python -m <module>` with `scripts/` first on its PYTHONPATH, so sub-package entry
points need no `sys.path` bootstrap and the caller's cwd is inherited.
"""

from __future__ import annotations

import os
import sys

import pytest

from core import entry


@pytest.mark.parametrize(
    ("handler", "module"),
    [
        ("compile.py", "compile"),
        ("lint.py", "lint"),
        ("core/piggyback_runner.py", "core.piggyback_runner"),
        ("dashboard/dashboard_stats.py", "dashboard.dashboard_stats"),
        ("preprocessors/inbox.py", "preprocessors.inbox"),
    ],
)
def test_module_for_maps_a_scripts_relative_path(handler: str, module: str) -> None:
    assert entry.module_for(handler) == module


def test_module_for_rejects_non_python_handlers() -> None:
    with pytest.raises(ValueError):
        entry.module_for("lib/common.sh")


def test_child_env_puts_scripts_first_and_keeps_the_callers_pythonpath() -> None:
    env = entry.child_env({"PYTHONPATH": "/caller/path", "HOME": "/h"})
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[0] == str(entry.SCRIPTS_DIR)
    assert parts[1:] == ["/caller/path"]
    assert env["HOME"] == "/h"


def test_child_env_without_an_inherited_pythonpath() -> None:
    env = entry.child_env({})
    assert env["PYTHONPATH"] == str(entry.SCRIPTS_DIR)


def test_child_env_defaults_to_the_live_environment(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/live")
    assert entry.child_env()["PYTHONPATH"].endswith(os.pathsep + "/live")


def test_python_m_builds_the_argv() -> None:
    assert entry.python_m("compile.py", "--file", "daily/x.md") == [
        sys.executable,
        "-m",
        "compile",
        "--file",
        "daily/x.md",
    ]


def test_scripts_dir_is_the_source_root() -> None:
    assert (entry.SCRIPTS_DIR / "core" / "entry.py").is_file()
    assert (entry.SCRIPTS_DIR / "cli.py").is_file()
