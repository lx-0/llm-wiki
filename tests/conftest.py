"""Test config — adds scripts/ to sys.path so domain/, adapters/, collectors/ resolve."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from core import daily_capture

from ._vault_isolation import install_write_guard, remove_write_guard

_UNSAFE_IN_NODEID = re.compile(r"[^A-Za-z0-9_.-]+")


def pytest_configure(config: pytest.Config) -> None:
    """Fail any write that escapes the checkout — see tests/_vault_isolation.py."""
    install_write_guard()


def pytest_unconfigure(config: pytest.Config) -> None:
    remove_write_guard()


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
