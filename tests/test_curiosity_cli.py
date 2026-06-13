"""Tests for `curiosity/cli.py` — dispatcher + helpers.

Tested narrowly: the dispatch routing (matches request.type to backend),
the read/list helpers (skip malformed JSON), and the --clear-done idempotency.
The interactive CLI paths (`_list`, `_run_oldest`, etc.) call `sys.exit`,
which makes them awkward to assert from pytest — we cover the seams they
depend on instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_dispatch_routes_email_deep_scan_to_email_backend(tmp_path, monkeypatch):
    from curiosity import cli

    request_path = _write(tmp_path / "request-x.json", {
        "type": "email-deep-scan",
        "status": "pending",
    })

    calls = []

    class FakeResult:
        success = True

    def fake_process_request(path, *, dry_run=False, **kwargs):
        calls.append((path, dry_run))
        return FakeResult()

    monkeypatch.setattr(cli.email_backend, "process_request", fake_process_request)

    ok = cli._dispatch(request_path, dry_run=False)
    assert ok is True
    assert calls == [(request_path, False)]


def test_dispatch_rejects_unsupported_type(tmp_path, monkeypatch):
    from curiosity import cli

    request_path = _write(tmp_path / "request-yt.json", {
        "type": "youtube-deep-watch",
        "status": "pending",
    })

    # Email backend should not be called.
    monkeypatch.setattr(
        cli.email_backend,
        "process_request",
        lambda *a, **kw: pytest.fail("email backend should not be called for non-email types"),
    )

    ok = cli._dispatch(request_path, dry_run=False)
    assert ok is False


def test_dispatch_handles_unreadable_file(tmp_path):
    from curiosity import cli

    request_path = tmp_path / "request-broken.json"
    request_path.write_text("{not valid json", encoding="utf-8")

    ok = cli._dispatch(request_path, dry_run=False)
    assert ok is False


def test_read_skips_malformed_json(tmp_path):
    from curiosity import cli

    p = tmp_path / "request-malformed.json"
    p.write_text("not even close to json", encoding="utf-8")

    assert cli._read(p) is None


def test_all_requests_returns_sorted_glob(tmp_path, monkeypatch):
    from curiosity import cli

    monkeypatch.setattr(cli, "REQUESTS_DIR", tmp_path)
    _write(tmp_path / "request-b.json", {"type": "email-deep-scan", "status": "pending"})
    _write(tmp_path / "request-a.json", {"type": "email-deep-scan", "status": "done"})
    (tmp_path / "not-a-request.json").write_text("{}", encoding="utf-8")

    paths = cli._all_requests()
    names = [p.name for p in paths]
    assert names == ["request-a.json", "request-b.json"]


# ── accept-all (bulk dispatch) — the operator's "accept all" function ──

def test_accept_all_dispatches_every_path_and_counts(tmp_path, monkeypatch):
    from curiosity import cli

    paths = [
        _write(tmp_path / "request-1.json", {"type": "email-deep-scan", "status": "pending"}),
        _write(tmp_path / "request-2.json", {"type": "email-deep-scan", "status": "pending"}),
        _write(tmp_path / "request-3.json", {"type": "folder-deep-scan", "status": "pending"}),
    ]
    seen = []

    def fake_dispatch(p, *, dry_run):
        seen.append(p)
        return p.name != "request-2.json"  # one failure

    monkeypatch.setattr(cli, "_dispatch", fake_dispatch)
    accepted, fails = cli._accept_all(paths, dry_run=False)
    assert seen == paths            # every request dispatched, in order
    assert (accepted, fails) == (2, 1)


def test_folder_consent_lines_lists_only_cloud_bound_files(tmp_path, monkeypatch):
    """Accept-all must surface WHICH files go to the cloud (folder-deep-scan)
    for one bulk informed consent — email requests are local, not listed."""
    from core.config import CONFIG
    from curiosity import cli

    monkeypatch.setattr(CONFIG.models, "folder_scan_provider", "claude-sdk")
    paths = [
        _write(tmp_path / "request-1.json", {"type": "email-deep-scan", "status": "pending"}),
        _write(tmp_path / "request-2.json", {
            "type": "folder-deep-scan", "status": "pending",
            "file_path": "Admin/Rechnungen/Hetzner-Mai.pdf"}),
    ]
    lines = cli._folder_consent_lines(paths)
    assert lines == [("Admin/Rechnungen/Hetzner-Mai.pdf", "claude-sdk")]


def test_walk_accept_all_key_dispatches_every_remaining(tmp_path, monkeypatch, capsys):
    """Drive the interactive walk: on the first card press [A] then confirm
    [y] → every remaining pending request is dispatched in one action. This
    is the wiring verification, not just the helper (REGEL #1)."""
    from curiosity import cli

    p1 = _write(tmp_path / "request-1.json", {
        "type": "folder-deep-scan", "status": "pending",
        "topic": "t1", "root_id": "docs", "file_path": "a/x.pdf",
        "rationale": "r"})
    p2 = _write(tmp_path / "request-2.json", {
        "type": "email-deep-scan", "status": "pending",
        "topic": "t2", "folder": "INBOX", "account": "kasserver", "rationale": "r"})
    monkeypatch.setattr(cli, "REQUESTS_DIR", tmp_path)

    dispatched = []
    monkeypatch.setattr(cli, "_dispatch",
                        lambda p, *, dry_run: dispatched.append(p) or True)
    keys = iter(["A", "y"])  # accept-all on card 1, then confirm
    monkeypatch.setattr(cli, "read_key", lambda: next(keys))

    with pytest.raises(SystemExit) as exc:
        cli._walk(dry_run=False)
    assert exc.value.code == 0
    assert dispatched == [p1, p2]            # BOTH remaining dispatched
    out = capsys.readouterr().out
    assert "will be LOADED and sent" in out  # folder consent shown
    assert "a/x.pdf" in out                  # the cloud-bound file listed


def test_walk_accept_all_cancelled_on_no(tmp_path, monkeypatch):
    """[A] then [n] cancels the bulk dispatch and returns to the per-item
    prompt — nothing is sent."""
    from curiosity import cli

    p1 = _write(tmp_path / "request-1.json", {
        "type": "folder-deep-scan", "status": "pending",
        "topic": "t1", "file_path": "a/x.pdf", "rationale": "r"})
    monkeypatch.setattr(cli, "REQUESTS_DIR", tmp_path)
    dispatched = []
    monkeypatch.setattr(cli, "_dispatch",
                        lambda p, *, dry_run: dispatched.append(p) or True)
    keys = iter(["A", "n", "q"])  # accept-all, decline, then quit
    monkeypatch.setattr(cli, "read_key", lambda: next(keys))

    with pytest.raises(SystemExit):
        cli._walk(dry_run=False)
    assert dispatched == []  # nothing sent — consent declined


def test_pending_filters_by_type_and_excludes_done(tmp_path, monkeypatch):
    """_pending lists all pending types by default (fixing the email-only
    hard-filter that hid folder requests) and filters by type on request."""
    from curiosity import cli

    monkeypatch.setattr(cli, "REQUESTS_DIR", tmp_path)
    _write(tmp_path / "request-1.json", {"type": "folder-deep-scan", "status": "pending"})
    _write(tmp_path / "request-2.json", {"type": "email-deep-scan", "status": "pending"})
    _write(tmp_path / "request-3.json", {"type": "folder-deep-scan", "status": "done"})
    _write(tmp_path / "request-4.json", {"type": "email-deep-scan", "status": "rejected"})

    names = lambda paths: sorted(p.name for p in paths)
    assert names(cli._pending()) == ["request-1.json", "request-2.json"]
    assert names(cli._pending("folder-deep-scan")) == ["request-1.json"]
    assert names(cli._pending("email-deep-scan")) == ["request-2.json"]
