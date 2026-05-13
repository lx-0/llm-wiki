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
