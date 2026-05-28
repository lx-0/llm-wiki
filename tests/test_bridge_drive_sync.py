"""Tests for the inbox-bridge core (scripts/bridge/drive_sync.py).

Subprocess is mocked — these tests do not invoke real rsync. End-to-end
verification is left to operator-side live runs (see SUMMARY).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _import():
    from bridge import drive_sync
    return drive_sync


def _ok(stdout: str = "", stderr: str = "", rc: int = 0):
    def fake_run(cmd, **kwargs):
        fake_run.calls.append(cmd)
        return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)
    fake_run.calls = []
    return fake_run


# ── validation ─────────────────────────────────────────────────────


def test_validate_rejects_non_dict():
    ds = _import()
    assert ds._validate([]) is not None
    assert ds._validate("not a dict") is not None  # type: ignore[arg-type]


def test_validate_requires_remote_and_local():
    ds = _import()
    assert ds._validate({"local": "/tmp/x"}) is not None
    assert ds._validate({"remote": "/tmp/x"}) is not None
    assert ds._validate({"remote": "", "local": "/tmp/x"}) is not None
    assert ds._validate({"remote": "/tmp/x", "local": "/tmp/y"}) is None


def test_validate_rejects_bad_mode():
    ds = _import()
    assert ds._validate({"remote": "/a", "local": "/b", "mode": "rsync"}) is not None
    assert ds._validate({"remote": "/a", "local": "/b", "mode": "move"}) is None
    assert ds._validate({"remote": "/a", "local": "/b", "mode": "copy"}) is None


# ── mapping name resolution ───────────────────────────────────────


def test_mapping_name_uses_explicit_name():
    ds = _import()
    assert ds._mapping_name({"name": "tablet-shots", "local": "/x"}) == "tablet-shots"


def test_mapping_name_falls_back_to_local_basename():
    ds = _import()
    assert ds._mapping_name({"local": "/home/u/foo/screenshots-tablet"}) == "screenshots-tablet"
    assert ds._mapping_name({"local": "/"}) == "<unnamed>"


# ── sync_one: skip paths ──────────────────────────────────────────


def test_sync_one_skips_invalid_mapping(tmp_path):
    ds = _import()
    r = ds.sync_one({"local": "/tmp/x"}, _run=_ok())
    assert r.status == "skipped"
    assert "remote" in r.reason


def test_sync_one_skips_disabled_mapping(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    r = ds.sync_one(
        {"remote": str(src), "local": str(tmp_path / "dst"), "enabled": False},
        _run=_ok(),
    )
    assert r.status == "skipped"
    assert r.reason == "disabled"


def test_sync_one_skips_missing_remote(tmp_path):
    ds = _import()
    fake = _ok()
    r = ds.sync_one(
        {"remote": str(tmp_path / "does-not-exist"), "local": str(tmp_path / "dst")},
        _run=fake,
    )
    assert r.status == "skipped"
    assert "remote_missing" in r.reason
    assert fake.calls == []  # rsync never invoked


# ── sync_one: happy path + rsync arg construction ─────────────────


def test_sync_one_invokes_rsync_with_move_flag(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    fake = _ok(stdout="sent 0 bytes")
    r = ds.sync_one(
        {"remote": str(src), "local": str(dst)},
        rsync_binary="/usr/bin/rsync",
        _run=fake,
    )
    assert r.status == "ok"
    assert dst.exists()  # local dir auto-created
    assert len(fake.calls) == 1
    cmd = fake.calls[0]
    assert cmd[0] == "/usr/bin/rsync"
    assert "-rt" in cmd
    assert "--remove-source-files" in cmd  # mode=move is the default
    assert "--exclude=.DS_Store" in cmd
    assert cmd[-2].endswith("/")  # source has trailing slash
    assert cmd[-1].endswith("/")  # dest has trailing slash


def test_sync_one_copy_mode_omits_remove_source_files(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    fake = _ok()
    ds.sync_one(
        {"remote": str(src), "local": str(tmp_path / "dst"), "mode": "copy"},
        rsync_binary="/usr/bin/rsync",
        _run=fake,
    )
    assert "--remove-source-files" not in fake.calls[0]


def test_sync_one_dry_run_adds_flag(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    fake = _ok()
    ds.sync_one(
        {"remote": str(src), "local": str(tmp_path / "dst")},
        dry_run=True,
        rsync_binary="/usr/bin/rsync",
        _run=fake,
    )
    assert "--dry-run" in fake.calls[0]


# ── sync_one: error paths ─────────────────────────────────────────


def test_sync_one_rsync_nonzero_marks_failed(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    fake = _ok(stderr="rsync: bad", rc=23)
    r = ds.sync_one(
        {"remote": str(src), "local": str(tmp_path / "dst")},
        rsync_binary="/usr/bin/rsync",
        _run=fake,
    )
    assert r.status == "failed"
    assert "rsync_exit_23" in r.reason
    assert r.stderr == "rsync: bad"


def test_sync_one_handles_missing_rsync_binary(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("rsync")

    r = ds.sync_one(
        {"remote": str(src), "local": str(tmp_path / "dst")},
        rsync_binary="/nonexistent/rsync",
        _run=fake_run,
    )
    assert r.status == "failed"
    assert "rsync_not_found" in r.reason


# ── run() summary ─────────────────────────────────────────────────


def test_run_empty_mappings_returns_empty_summary():
    ds = _import()
    summary = ds.run([], _run=_ok())
    assert summary.results == []
    assert summary.exit_code == 0
    assert summary.ok_count == 0


def test_run_aggregates_status_counts(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    fake = _ok()
    mappings = [
        {"remote": str(src), "local": str(tmp_path / "ok"), "name": "good"},
        {"remote": str(tmp_path / "missing"), "local": str(tmp_path / "ny"), "name": "gone"},
        {"local": str(tmp_path / "broken"), "name": "broken"},  # invalid
    ]
    summary = ds.run(mappings, rsync_binary="/usr/bin/rsync", _run=fake)
    assert summary.ok_count == 1
    assert summary.skipped_count == 2
    assert summary.failed_count == 0
    assert summary.exit_code == 0


def test_run_exit_code_nonzero_on_failure(tmp_path):
    ds = _import()
    src = tmp_path / "src"
    src.mkdir()
    fake = _ok(rc=23)
    summary = ds.run(
        [{"remote": str(src), "local": str(tmp_path / "dst")}],
        rsync_binary="/usr/bin/rsync",
        _run=fake,
    )
    assert summary.exit_code == 1
    assert summary.failed_count == 1
