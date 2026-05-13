"""Tests for `curiosity/backends/email.py` — the deep-scan consumer.

Architecture: process_request loads a request JSON, resolves a Mailbox
adapter for the account, calls scan_deep, renders markdown, and marks
the request done. We test the full happy path + error branches without
touching any real mailbox by monkeypatching `resolve_reader`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pytest

from domain.mail import Message, MessageMeta


# ── Fixtures ─────────────────────────────────────────────────────────


class _FakeReader:
    """In-memory MailboxReader yielding canned messages from scan_deep."""

    def __init__(self, account_id: str, messages: list[Message]) -> None:
        self._account_id = account_id
        self._messages = messages

    def list_folders(self) -> list[str]:
        return sorted({m.meta.folder for m in self._messages})

    def scan_metadata(self, folder=None, since=None) -> Iterator[MessageMeta]:
        for m in self._messages:
            yield m.meta

    def scan_deep(self, folder: str, limit: int = 0, since: datetime | None = None) -> Iterator[Message]:
        emitted = 0
        for m in self._messages:
            if m.meta.folder != folder:
                continue
            yield m
            emitted += 1
            if limit and emitted >= limit:
                return


def _msg(folder: str, subject: str, body: str, when: datetime | None = None) -> Message:
    when = when or datetime(2026, 5, 13, 12, 0, 0)
    return Message(
        meta=MessageMeta(
            id=f"m-{subject}",
            account_id="testacct",
            folder=folder,
            from_addr="sender@example.com",
            to_addrs=("recipient@example.com",),
            subject=subject,
            date=when,
            size_bytes=len(body),
        ),
        body_text=body,
    )


@pytest.fixture
def sample_messages() -> list[Message]:
    return [
        _msg("INBOX/Work", "First", "Body of first message"),
        _msg("INBOX/Work", "Second", "Body of second message"),
        _msg("INBOX/Other", "Off-topic", "Should not appear"),
    ]


@pytest.fixture
def request_path(tmp_path: Path) -> Path:
    """A pending email-deep-scan request file at a clean temp path."""
    p = tmp_path / "request-customer-y-2026-05-13.json"
    p.write_text(
        json.dumps({
            "type": "email-deep-scan",
            "status": "pending",
            "folder": "INBOX/Work",
            "account": "testacct",
            "model": "gemma4:e4b",
            "topic": "Customer Y meeting prep",
            "rationale": "Compile mentioned Customer Y but no article exists yet.",
            "source": "daily/2026-05-13.md",
            "created": "2026-05-13T11:00:00+00:00",
        }, indent=2),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def patched_backend(monkeypatch, tmp_path, sample_messages):
    """Wire the email backend to a tmp_path vault + FakeReader + fake CONFIG."""
    from curiosity.backends import email as backend

    fake_account = {"email": "alex@example.com", "reader": {"kind": "fake"}}

    monkeypatch.setattr(backend, "DEEP_SCAN_DIR", tmp_path / "raw" / "notes" / "email")
    monkeypatch.setattr(backend, "ROOT_DIR", tmp_path)

    class _CONFIG:
        class personal:
            primary_account = "testacct"
            accounts = {"testacct": fake_account}

    monkeypatch.setattr(backend, "CONFIG", _CONFIG)
    monkeypatch.setattr(
        backend,
        "resolve_reader",
        lambda account: _FakeReader("testacct", sample_messages),
    )
    return backend


# ── _render: pure-function shape ────────────────────────────────────


def test_render_includes_frontmatter_and_message_bodies(patched_backend, sample_messages):
    request = {
        "type": "email-deep-scan",
        "folder": "INBOX/Work",
        "topic": "Customer Y",
        "rationale": "Compile gap",
        "source": "daily/2026-05-13.md",
        "created": "2026-05-13T11:00:00+00:00",
    }
    out = patched_backend._render(request, [m for m in sample_messages if m.meta.folder == "INBOX/Work"], "testacct")

    assert out.startswith("---\n")
    assert "type: note" in out
    assert "kind: email-deep-scan" in out
    assert 'topic: "Customer Y"' in out
    assert "account: testacct" in out
    assert "messages: 2" in out
    # Bodies must be inside code-fences
    assert "Body of first message" in out
    assert "Body of second message" in out


def test_render_handles_empty_message_list(patched_backend):
    request = {
        "type": "email-deep-scan",
        "folder": "INBOX/Empty",
        "topic": "Nothing here",
        "rationale": "Test the empty branch",
        "source": "daily/x.md",
        "created": "2026-05-13T11:00:00+00:00",
    }
    out = patched_backend._render(request, [], "testacct")
    assert "messages: 0" in out
    assert "_No messages matched._" in out


def test_render_truncates_long_body(patched_backend):
    long_body = "X" * 20000
    msg = _msg("INBOX/Work", "Long", long_body)
    request = {
        "type": "email-deep-scan", "folder": "INBOX/Work", "topic": "T",
        "rationale": "R", "source": "s", "created": "c",
    }
    out = patched_backend._render(request, [msg], "testacct")
    assert "[truncated]" in out


# ── process_request: happy path + error branches ────────────────────


def test_process_request_happy_path(patched_backend, request_path, tmp_path):
    result = patched_backend.process_request(request_path)

    assert result.success
    assert result.messages_pulled == 2  # 2 messages in INBOX/Work, 1 off-topic skipped
    assert result.output_path is not None
    assert result.output_path.exists()
    # Output file lives under the patched DEEP_SCAN_DIR (tmp_path)
    assert "deep-customer-y-2026-05-13.md" in result.output_path.name

    # Request file gets status:done + processed_at
    updated = json.loads(request_path.read_text(encoding="utf-8"))
    assert updated["status"] == "done"
    assert "processed_at" in updated
    assert "output" in updated
    assert updated["messages_pulled"] == 2


def test_process_request_idempotent_when_already_done(patched_backend, request_path):
    # First run
    first = patched_backend.process_request(request_path)
    assert first.success

    # Second run should be no-op (status already done)
    second = patched_backend.process_request(request_path)
    assert second.success
    assert second.output_path is None
    assert second.messages_pulled == 0


def test_process_request_missing_account_in_config(patched_backend, request_path, monkeypatch):
    # Strip the account from CONFIG.personal.accounts
    class _EmptyCONFIG:
        class personal:
            primary_account = "testacct"
            accounts = {}
    monkeypatch.setattr(patched_backend, "CONFIG", _EmptyCONFIG)

    result = patched_backend.process_request(request_path)
    assert not result.success
    assert "not in CONFIG.personal.accounts" in result.error

    # Status reflects the error
    updated = json.loads(request_path.read_text(encoding="utf-8"))
    assert updated["status"] == "error"
    assert "last_error" in updated


def test_process_request_unresolved_reader(patched_backend, request_path, monkeypatch):
    monkeypatch.setattr(patched_backend, "resolve_reader", lambda account: None)

    result = patched_backend.process_request(request_path)
    assert not result.success
    assert "no reader adapter" in result.error


def test_process_request_wrong_type(patched_backend, tmp_path):
    p = tmp_path / "request-other.json"
    p.write_text(json.dumps({"type": "youtube-deep-watch", "status": "pending"}), encoding="utf-8")

    result = patched_backend.process_request(p)
    assert not result.success
    assert "unsupported type" in result.error


def test_process_request_missing_file(tmp_path):
    from curiosity.backends import email as backend
    result = backend.process_request(tmp_path / "does-not-exist.json")
    assert not result.success
    assert "not found" in result.error


def test_process_request_invalid_json(patched_backend, tmp_path):
    p = tmp_path / "request-bad.json"
    p.write_text("{not valid json", encoding="utf-8")

    result = patched_backend.process_request(p)
    assert not result.success
    assert "invalid JSON" in result.error


def test_process_request_dry_run(patched_backend, request_path):
    result = patched_backend.process_request(request_path, dry_run=True)
    assert result.success
    assert result.output_path is None
    # Status unchanged in dry-run
    updated = json.loads(request_path.read_text(encoding="utf-8"))
    assert updated["status"] == "pending"


# ── list_pending: queue filtering ────────────────────────────────────


def test_list_pending_excludes_done(tmp_path):
    from curiosity.backends import email as backend

    requests_dir = tmp_path / "requests"
    requests_dir.mkdir()
    (requests_dir / "request-a.json").write_text(json.dumps({
        "type": "email-deep-scan", "status": "pending",
    }), encoding="utf-8")
    (requests_dir / "request-b.json").write_text(json.dumps({
        "type": "email-deep-scan", "status": "done",
    }), encoding="utf-8")
    (requests_dir / "request-c.json").write_text(json.dumps({
        "type": "email-deep-scan", "status": "error",
    }), encoding="utf-8")
    (requests_dir / "request-d.json").write_text(json.dumps({
        "type": "youtube-deep-watch", "status": "pending",
    }), encoding="utf-8")

    pending = backend.list_pending(requests_dir)
    # a + c remain (pending + error); b excluded (done); d excluded (wrong type)
    names = sorted(p.name for p in pending)
    assert names == ["request-a.json", "request-c.json"]


def test_list_pending_empty_dir(tmp_path):
    from curiosity.backends import email as backend
    assert backend.list_pending(tmp_path / "missing") == []
    (tmp_path / "empty").mkdir()
    assert backend.list_pending(tmp_path / "empty") == []
