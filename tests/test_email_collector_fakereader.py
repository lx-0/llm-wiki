"""S01 proof — EmailCollector consumes a FakeReader through the seam.

Tests the architecture without touching any real backend (no mbox files,
no IMAP, no Gmail API). FakeReader implements the `MailboxReader` Protocol
in-memory; pytest exercises EmailCollector against it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator

import pytest

from adapters.mailbox import MailboxReader
from domain.mail import Message, MessageMeta


# ── Fixtures ─────────────────────────────────────────────────────────


class FakeMailboxReader:
    """In-memory MailboxReader. Seeded with a list of MessageMeta."""

    def __init__(self, account_id: str, messages: list[MessageMeta]) -> None:
        self._account_id = account_id
        self._messages = messages

    def list_folders(self) -> list[str]:
        return sorted({m.folder for m in self._messages})

    def scan_metadata(
        self, folder: str | None = None, since: datetime | None = None
    ) -> Iterator[MessageMeta]:
        for m in self._messages:
            if folder is not None and m.folder != folder:
                continue
            if since is not None and m.date < since:
                continue
            yield m

    def scan_deep(
        self, folder: str, limit: int = 0, since: datetime | None = None
    ) -> Iterator[Message]:
        # Not used by metadata-only EmailCollector tests.
        for m in self._messages:
            if m.folder != folder:
                continue
            yield Message(meta=m, body_text="(fake body)")


@pytest.fixture
def sample_messages() -> list[MessageMeta]:
    return [
        MessageMeta(
            id="1",
            account_id="testacct",
            folder="INBOX",
            from_addr="alice@example.com",
            to_addrs=("operator@example.com",),
            subject="hello",
            date=datetime(2026, 5, 1, 10, 0),
            size_bytes=1234,
        ),
        MessageMeta(
            id="2",
            account_id="testacct",
            folder="INBOX/Work",
            from_addr="bob@example.com",
            to_addrs=("operator@example.com",),
            subject="invoice",
            date=datetime(2026, 5, 1, 11, 30),
            size_bytes=2345,
        ),
        MessageMeta(
            id="3",
            account_id="testacct",
            folder="INBOX",
            from_addr="alice@example.com",
            to_addrs=("operator@example.com",),
            subject="follow-up",
            date=datetime(2026, 5, 2, 9, 15),
            size_bytes=890,
        ),
    ]


# ── Protocol conformance ─────────────────────────────────────────────


def test_fake_reader_satisfies_protocol(sample_messages: list[MessageMeta]) -> None:
    """FakeReader must satisfy the MailboxReader Protocol — runtime check."""
    reader = FakeMailboxReader("testacct", sample_messages)
    assert isinstance(reader, MailboxReader)


def test_fake_reader_streams_metadata(sample_messages: list[MessageMeta]) -> None:
    reader = FakeMailboxReader("testacct", sample_messages)
    out = list(reader.scan_metadata())
    assert len(out) == 3
    inbox_only = list(reader.scan_metadata(folder="INBOX"))
    assert len(inbox_only) == 2
    since_may2 = list(reader.scan_metadata(since=datetime(2026, 5, 2, 0, 0)))
    assert len(since_may2) == 1
    assert since_may2[0].subject == "follow-up"


# ── EmailCollector via injected reader ───────────────────────────────


def test_email_collector_renders_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_messages: list[MessageMeta],
) -> None:
    """Drive EmailCollector with a FakeReader; expect a markdown report on disk."""

    # Stub CONFIG.personal.accounts so the collector finds one account.
    from collectors import email as email_mod

    fake_reader = FakeMailboxReader("testacct", sample_messages)

    class _PersonalStub:
        accounts = {"testacct": {"reader": {"kind": "fake"}}}

    class _ConfigStub:
        personal = _PersonalStub()

    monkeypatch.setattr(email_mod, "CONFIG", _ConfigStub())
    monkeypatch.setattr(email_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(email_mod, "resolve_reader", lambda account: fake_reader)

    collector = email_mod.EmailCollector()
    assert collector.is_configured()

    result = collector.run(dry_run=False)
    assert len(result.files_written) == 1
    report = result.files_written[0]
    assert report.exists()

    content = report.read_text(encoding="utf-8")
    assert "# Email overview — testacct" in content
    assert "alice@example.com" in content
    assert "INBOX/Work" in content


def test_email_collector_skips_unconfigured_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Account whose reader.kind doesn't resolve → silently skipped (graceful agnostic)."""
    from collectors import email as email_mod

    class _PersonalStub:
        accounts = {"unknown_kind": {"reader": {"kind": "totally-made-up"}}}

    class _ConfigStub:
        personal = _PersonalStub()

    monkeypatch.setattr(email_mod, "CONFIG", _ConfigStub())
    monkeypatch.setattr(email_mod, "ROOT_DIR", tmp_path)
    # resolve_reader returns None for unknown kinds — that's the real behavior

    collector = email_mod.EmailCollector()
    assert not collector.is_configured()

    result = collector.run(dry_run=False)
    assert result.files_written == ()
    assert "no accounts" in result.message.lower() or "no-op" in result.message.lower()


def test_email_collector_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_messages: list[MessageMeta],
) -> None:
    """--dry-run preserves the no-side-effects contract."""
    from collectors import email as email_mod

    fake_reader = FakeMailboxReader("testacct", sample_messages)

    class _PersonalStub:
        accounts = {"testacct": {"reader": {"kind": "fake"}}}

    class _ConfigStub:
        personal = _PersonalStub()

    monkeypatch.setattr(email_mod, "CONFIG", _ConfigStub())
    monkeypatch.setattr(email_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(email_mod, "resolve_reader", lambda account: fake_reader)

    result = email_mod.EmailCollector().run(dry_run=True)
    assert result.files_written == ()
    # No files anywhere under tmp_path.
    written = list(tmp_path.rglob("*.md"))
    assert written == []


# ── Registry ─────────────────────────────────────────────────────────


def test_registry_registers_email_collector() -> None:
    from collectors import all_collectors, get_collector

    names = [c.SPEC.name for c in all_collectors()]
    assert "email" in names
    assert get_collector("email") is not None
    assert get_collector("nonexistent") is None
