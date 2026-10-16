"""Test config — vault-write isolation, the snapshot flag, per-test path sinks.

`scripts/` and `hooks/` are on `sys.path` through `[tool.pytest.ini_options] pythonpath`
(applied before this file is imported); nothing here touches `sys.path`.
"""

from __future__ import annotations

import re
import sys

import pytest

from core import daily_capture
from core.paths import ROOT_DIR

from ._vault_isolation import (
    changed_neighbours,
    install_write_guard,
    neighbours,
    remove_write_guard,
)

_UNSAFE_IN_NODEID = re.compile(r"[^A-Za-z0-9_.-]+")
_NEIGHBOURS = pytest.StashKey[dict[str, int]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help=(
            "Rewrite tests/golden/oracle/* and tests/golden/bash/* from the current output "
            "(see tests/_oracle.py)."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Fail any write that escapes the checkout — see tests/_vault_isolation.py."""
    install_write_guard()


def pytest_unconfigure(config: pytest.Config) -> None:
    remove_write_guard()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_NEIGHBOURS] = neighbours()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if anything next to the checkout changed — the writes of child
    processes, which the in-process guard cannot see (tests/_vault_isolation.py)."""
    before = session.config.stash.get(_NEIGHBOURS, None)
    if before is None:
        return
    moved = changed_neighbours(before, neighbours())
    if moved:
        sys.stderr.write(
            f"\nThe test run changed {', '.join(moved)} next to the checkout ({ROOT_DIR}).\n"
            "A test ran the engine in a child process that wrote outside its vault — see "
            "tests/_vault_isolation.py.\n"
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def isolated_vault_paths(request, tmp_path_factory, monkeypatch):
    """Repoint vault-content path constants at a per-test sink.

    `core.paths.ROOT_DIR` is the checkout's parent in a dev checkout, so the
    constants derived from it point outside the repo. Redirect the ones tests
    reach; the write guard catches the ones nobody thought of yet. A test that
    patches the same constant itself still wins — its `monkeypatch` runs later.
    """
    sink = (
        tmp_path_factory.getbasetemp()
        / "vault-sink"
        / _UNSAFE_IN_NODEID.sub("_", request.node.nodeid)[-120:]
    )
    monkeypatch.setattr(daily_capture, "DAILY_DIR", sink / "daily")
