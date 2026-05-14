"""S01 proof — EmailCollector consumes a FakeReader through the seam.

Tests the architecture without touching any real backend (no mbox files,
no IMAP, no Gmail API). FakeReader implements the `MailboxReader` Protocol
in-memory; pytest exercises EmailCollector against it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from adapters.mailbox import MailboxReader, MailboxReadError
from domain.mail import Message, MessageMeta


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_email_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point EMAIL_STATE_FILE into tmp_path so no test touches real engine state."""
    from collectors import email_collector as email_mod

    state_file = tmp_path / "email-state.json"
    monkeypatch.setattr(email_mod, "EMAIL_STATE_FILE", state_file)
    return state_file


class FakeMailboxReader:
    """In-memory MailboxReader. Seeded with a list of MessageMeta.

    `raises=` makes `scan_metadata` raise instead of yielding — for testing
    the collector's failure path (a real reader raises MailboxReadError on
    connect/login failure).
    """

    def __init__(
        self,
        account_id: str,
        messages: list[MessageMeta],
        *,
        raises: Exception | None = None,
    ) -> None:
        self._account_id = account_id
        self._messages = messages
        self._raises = raises

    def list_folders(self) -> list[str]:
        return sorted({m.folder for m in self._messages})

    def scan_metadata(
        self, folder: str | None = None, since: datetime | None = None
    ) -> Iterator[MessageMeta]:
        if self._raises is not None:
            raise self._raises
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


@pytest.fixture
def tz_messages() -> list[MessageMeta]:
    """tz-aware messages — mirrors the real Thunderbird reader, which
    normalises every Date header to UTC-aware. The incremental path
    compares against a tz-aware `since`, so its fixtures must be aware too.
    """
    def _msg(mid: str, folder: str, sender: str, dt: datetime) -> MessageMeta:
        return MessageMeta(
            id=mid,
            account_id="testacct",
            folder=folder,
            from_addr=sender,
            to_addrs=("operator@example.com",),
            subject=f"subject-{mid}",
            date=dt,
            size_bytes=1024,
        )

    return [
        _msg("1", "INBOX", "alice@example.com", datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)),
        _msg("2", "INBOX/Work", "bob@example.com", datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)),
        _msg("3", "INBOX", "alice@example.com", datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)),
    ]


def _email_mod_with_account(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reader: object):
    """Wire EmailCollector to a single fake-account + injected reader."""
    from collectors import email_collector as email_mod

    class _PersonalStub:
        accounts = {"testacct": {"reader": {"kind": "fake"}}}

    class _ConfigStub:
        personal = _PersonalStub()

    monkeypatch.setattr(email_mod, "CONFIG", _ConfigStub())
    monkeypatch.setattr(email_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(email_mod, "resolve_reader", lambda account: reader)
    return email_mod


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
    from collectors import email_collector as email_mod

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
    from collectors import email_collector as email_mod

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
    from collectors import email_collector as email_mod

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


# ── Incremental delta path ───────────────────────────────────────────


def test_incremental_first_run_baselines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tz_messages: list[MessageMeta],
    _isolate_email_state: Path,
) -> None:
    """First incremental run for an account: record a watermark, emit nothing.

    The operator's one-time bulk ingest must not be re-dumped as a "delta".
    """
    email_mod = _email_mod_with_account(
        monkeypatch, tmp_path, FakeMailboxReader("testacct", tz_messages)
    )

    result = email_mod.EmailCollector().run(incremental=True)

    assert result.files_written == ()
    assert "baselined" in result.message
    assert list(tmp_path.rglob("*.md")) == []
    # Watermark persisted for the account.
    state = json.loads(_isolate_email_state.read_text(encoding="utf-8"))
    assert state["accounts"]["testacct"]["last_run_ts"]


def test_incremental_emits_delta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tz_messages: list[MessageMeta],
    _isolate_email_state: Path,
) -> None:
    """With a watermark in place, only messages newer than it land in the delta."""
    _isolate_email_state.write_text(
        json.dumps({"accounts": {"testacct": {"last_run_ts": "2026-05-05T00:00:00+00:00"}}}),
        encoding="utf-8",
    )
    email_mod = _email_mod_with_account(
        monkeypatch, tmp_path, FakeMailboxReader("testacct", tz_messages)
    )

    result = email_mod.EmailCollector().run(incremental=True)

    assert len(result.files_written) == 1
    report = result.files_written[0]
    assert report.name.startswith("testacct-delta-")
    content = report.read_text(encoding="utf-8")
    assert "type: email-delta" in content
    assert "# Email Delta — testacct" in content
    # msg 2 (May 10, INBOX/Work) + msg 3 (May 12, INBOX) are after the
    # watermark; msg 1 (May 1) is not. Per-message lines carry the subject —
    # the signal the compiler distils from.
    assert "## INBOX/Work" in content
    assert "— subject-2" in content and "— subject-3" in content
    assert "bob@example.com" in content
    # Per-message line carries date+time, not just the date.
    assert "`05-10 09:00`" in content and "`05-12 15:00`" in content
    assert "subject-1" not in content  # the pre-watermark message is excluded
    # Watermark advanced past the seeded value.
    state = json.loads(_isolate_email_state.read_text(encoding="utf-8"))
    assert state["accounts"]["testacct"]["last_run_ts"] != "2026-05-05T00:00:00+00:00"


def test_incremental_no_new_mail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tz_messages: list[MessageMeta],
    _isolate_email_state: Path,
) -> None:
    """Watermark newer than all mail: no report, but the watermark still advances."""
    _isolate_email_state.write_text(
        json.dumps({"accounts": {"testacct": {"last_run_ts": "2026-05-20T00:00:00+00:00"}}}),
        encoding="utf-8",
    )
    email_mod = _email_mod_with_account(
        monkeypatch, tmp_path, FakeMailboxReader("testacct", tz_messages)
    )

    result = email_mod.EmailCollector().run(incremental=True)

    assert result.files_written == ()
    assert result.files_skipped == 1
    state = json.loads(_isolate_email_state.read_text(encoding="utf-8"))
    assert state["accounts"]["testacct"]["last_run_ts"] != "2026-05-20T00:00:00+00:00"


def test_incremental_dry_run_leaves_state_untouched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tz_messages: list[MessageMeta],
    _isolate_email_state: Path,
) -> None:
    """--dry-run on the incremental path writes neither a report nor the watermark."""
    seed = {"accounts": {"testacct": {"last_run_ts": "2026-05-05T00:00:00+00:00"}}}
    _isolate_email_state.write_text(json.dumps(seed), encoding="utf-8")
    email_mod = _email_mod_with_account(
        monkeypatch, tmp_path, FakeMailboxReader("testacct", tz_messages)
    )

    result = email_mod.EmailCollector().run(incremental=True, dry_run=True)

    assert result.files_written == ()
    assert list(tmp_path.rglob("*.md")) == []
    assert json.loads(_isolate_email_state.read_text(encoding="utf-8")) == seed


def test_incremental_does_not_advance_watermark_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    _isolate_email_state: Path,
) -> None:
    """A MailboxReadError holds the watermark exactly where it was — so the
    next run retries the same window — and records last_error. The failure
    is surfaced in RunResult.errors, never silently swallowed.
    """
    seed_ts = "2026-05-05T00:00:00+00:00"
    _isolate_email_state.write_text(
        json.dumps({"accounts": {"testacct": {"last_run_ts": seed_ts}}}),
        encoding="utf-8",
    )
    failing_reader = FakeMailboxReader(
        "testacct", [], raises=MailboxReadError("login failed: bad app password")
    )
    email_mod = _email_mod_with_account(monkeypatch, tmp_path, failing_reader)

    result = email_mod.EmailCollector().run(incremental=True)

    # Failure surfaced, no delta written.
    assert result.files_written == ()
    assert any("login failed" in e for e in result.errors)
    assert "FAILED" in result.message
    # Watermark HELD (not advanced), error recorded + timestamped.
    entry = json.loads(_isolate_email_state.read_text(encoding="utf-8"))["accounts"]["testacct"]
    assert entry["last_run_ts"] == seed_ts
    assert "login failed" in entry["last_error"]
    assert entry["last_error_at"]


def test_incremental_clears_last_error_on_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tz_messages: list[MessageMeta],
    _isolate_email_state: Path,
) -> None:
    """A successful scan clears a stale last_error — the state file always
    reflects current health, not a frozen old failure."""
    _isolate_email_state.write_text(
        json.dumps({"accounts": {"testacct": {
            "last_run_ts": "2026-05-05T00:00:00+00:00",
            "last_error": "login failed earlier",
            "last_error_at": "2026-05-13T00:00:00+00:00",
        }}}),
        encoding="utf-8",
    )
    email_mod = _email_mod_with_account(
        monkeypatch, tmp_path, FakeMailboxReader("testacct", tz_messages)
    )

    email_mod.EmailCollector().run(incremental=True)

    entry = json.loads(_isolate_email_state.read_text(encoding="utf-8"))["accounts"]["testacct"]
    assert "last_error" not in entry
    assert "last_error_at" not in entry
    assert entry["last_run_ts"] != "2026-05-05T00:00:00+00:00"  # advanced on success


def test_load_state_migrates_legacy_shape(
    monkeypatch: pytest.MonkeyPatch,
    _isolate_email_state: Path,
) -> None:
    """Legacy per-mbox state → per-account watermarks seeded from last_incremental."""
    from collectors import email_collector as email_mod

    _isolate_email_state.write_text(
        json.dumps({
            "mboxes": {"ImapMail/server/INBOX": {"size": 1, "count": 1, "last_scan": "2026-04-01"}},
            "last_incremental": "2026-05-01",
        }),
        encoding="utf-8",
    )

    class _PersonalStub:
        accounts = {"work": {}, "private": {}}

    class _ConfigStub:
        personal = _PersonalStub()

    monkeypatch.setattr(email_mod, "CONFIG", _ConfigStub())

    state = email_mod._load_state()

    assert state == {
        "accounts": {
            "work": {"last_run_ts": "2026-05-01T00:00:00+00:00"},
            "private": {"last_run_ts": "2026-05-01T00:00:00+00:00"},
        }
    }


# ── Registry ─────────────────────────────────────────────────────────


def test_registry_registers_email_collector() -> None:
    from collectors import all_collectors, get_collector

    names = [c.SPEC.name for c in all_collectors()]
    assert "email" in names
    assert get_collector("email") is not None
    assert get_collector("nonexistent") is None
