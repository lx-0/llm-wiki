"""Global compile-lock: only one compile.py runs at a time.

Motivated by 2026-05-15 incident where parallel SessionEnd hooks each
spawned `compile.py --file daily/<X>.md` for the same daily file. Three
concurrent bundled-CLI subprocesses competed for Claude subscription quota
and crashed mid-stream with kind=unknown / empty stderr. Engine-level
consecutive-failure abort caught the cascade but the work was already lost.

The fix: compile.py acquires an exclusive non-blocking flock on
STATE_DIR/compile.lock at the top of main(). Second invocation while the
first holds the lock exits cleanly with a skip message — no work, no error.
"""

from __future__ import annotations

import fcntl
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_PY = REPO_ROOT / "scripts" / "compile.py"


@pytest.fixture
def isolated_lock_path(tmp_path, monkeypatch):
    """Redirect STATE_DIR so the test's lock file lives in tmp_path."""
    monkeypatch.setenv("WIKI_STATE_DIR_OVERRIDE", str(tmp_path))
    return tmp_path / "compile.lock"


def test_acquire_compile_lock_returns_handle_when_uncontested(tmp_path):
    """Direct unit test of the helper: returns an fd-bearing handle."""
    import compile as compile_mod

    lock_path = tmp_path / "compile.lock"
    handle = compile_mod._acquire_exclusive_lock(lock_path)
    try:
        assert handle is not None
    finally:
        if handle is not None:
            handle.close()


def test_acquire_compile_lock_returns_none_when_contended(tmp_path):
    """Second acquire while first is held returns None."""
    import compile as compile_mod

    lock_path = tmp_path / "compile.lock"
    first = compile_mod._acquire_exclusive_lock(lock_path)
    try:
        assert first is not None
        second = compile_mod._acquire_exclusive_lock(lock_path)
        assert second is None, "expected None on contention, got handle"
    finally:
        if first is not None:
            first.close()


def test_acquire_compile_lock_recovers_after_release(tmp_path):
    """Releasing the first handle lets the next acquire succeed."""
    import compile as compile_mod

    lock_path = tmp_path / "compile.lock"
    first = compile_mod._acquire_exclusive_lock(lock_path)
    assert first is not None
    first.close()

    second = compile_mod._acquire_exclusive_lock(lock_path)
    try:
        assert second is not None, "expected handle after release, got None"
    finally:
        if second is not None:
            second.close()
