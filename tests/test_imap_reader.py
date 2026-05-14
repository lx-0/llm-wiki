"""ImapReader — exercises the generic IMAP reader against a fake IMAPClient.

No real IMAP server: `imapclient.IMAPClient` is monkeypatched with an
in-memory fake. The fake's `search()` deliberately ignores SINCE criteria
(real IMAP SINCE is date-granular and returns a superset) so the tests
exercise ImapReader's own precise-watermark + undated-skip re-filter.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from adapters.mailbox import MailboxReader, resolve_reader
from adapters.mailbox.imap import ImapReader

imapclient = pytest.importorskip("imapclient")
from imapclient.response_types import Address, Envelope  # noqa: E402


# ── Fake IMAPClient ──────────────────────────────────────────────────


def _envelope(subject: str, mailbox: str, host: str, date: datetime | None) -> Envelope:
    return Envelope(
        date=date,
        subject=subject.encode(),
        from_=(Address(b"", None, mailbox.encode(), host.encode()),),
        sender=None,
        reply_to=None,
        to=None,
        cc=None,
        bcc=None,
        in_reply_to=None,
        message_id=f"<{subject}@test>".encode(),
    )


def _fetch_row(subject: str, sender: str, date: datetime | None, *, internaldate: bool = True) -> dict:
    mailbox, _, host = sender.partition("@")
    row: dict = {
        b"ENVELOPE": _envelope(subject, mailbox, host, date),
        b"RFC822.SIZE": 4096,
    }
    if internaldate and date is not None:
        row[b"INTERNALDATE"] = date
    return row


class FakeIMAPClient:
    """In-memory IMAPClient stand-in. FOLDERS: {folder_name: {uid: fetch_row}}."""

    FOLDERS: dict[str, dict[int, dict]] = {}
    RAISE_ON_LOGIN = False

    def __init__(self, host, port=993, ssl=True) -> None:
        # Faithful to imapclient 3.x: normalise_times is an instance
        # attribute the real IMAPClient sets in __init__, NOT a ctor kwarg.
        # ImapReader._connect flips it to False after construction.
        self.host = host
        self.normalise_times = True
        self._selected: str | None = None

    def login(self, user, password):
        if FakeIMAPClient.RAISE_ON_LOGIN:
            raise RuntimeError("authentication failed")

    def list_folders(self):
        return [((), b"/", name) for name in FakeIMAPClient.FOLDERS]

    def select_folder(self, name, readonly=False):
        self._selected = name

    def search(self, criteria):  # noqa: ARG002  fake ignores SINCE on purpose
        return list(FakeIMAPClient.FOLDERS.get(self._selected, {}))

    def fetch(self, uids, data_items):  # noqa: ARG002
        rows = FakeIMAPClient.FOLDERS.get(self._selected, {})
        return {uid: rows[uid] for uid in uids if uid in rows}

    def logout(self):
        pass


@pytest.fixture(autouse=True)
def _fake_imapclient(monkeypatch: pytest.MonkeyPatch):
    """Swap in the fake + a clean slate per test."""
    FakeIMAPClient.FOLDERS = {}
    FakeIMAPClient.RAISE_ON_LOGIN = False
    monkeypatch.setattr("imapclient.IMAPClient", FakeIMAPClient)
    monkeypatch.setenv("TEST_IMAP_PASS", "app-password-1234")


def _reader(**kw) -> ImapReader:
    return ImapReader(
        "testacct",
        host=kw.get("host", "imap.example.com"),
        pass_env=kw.get("pass_env", "TEST_IMAP_PASS"),
        user_env=kw.get("user_env", ""),
        default_user=kw.get("default_user", "alex@example.com"),
        folders=kw.get("folders"),
    )


# ── Protocol conformance ─────────────────────────────────────────────


def test_imap_reader_satisfies_protocol() -> None:
    assert isinstance(_reader(), MailboxReader)


# ── scan_metadata ────────────────────────────────────────────────────


def test_scan_metadata_builds_message_meta() -> None:
    FakeIMAPClient.FOLDERS = {
        "INBOX": {
            1: _fetch_row("hello", "alice@example.com", datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)),
        },
        "INBOX/Work": {
            2: _fetch_row("invoice", "bob@vendor.com", datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)),
        },
    }
    metas = list(_reader().scan_metadata())

    assert {m.folder for m in metas} == {"INBOX", "INBOX/Work"}
    by_subject = {m.subject: m for m in metas}
    assert by_subject["hello"].from_addr == "alice@example.com"
    assert by_subject["invoice"].from_addr == "bob@vendor.com"
    assert all(m.date.tzinfo is not None for m in metas)  # never naive
    assert by_subject["hello"].id == "1"


def test_scan_metadata_since_drops_old_and_undated() -> None:
    FakeIMAPClient.FOLDERS = {
        "INBOX": {
            1: _fetch_row("old", "a@x.com", datetime(2026, 5, 1, tzinfo=timezone.utc)),
            2: _fetch_row("new", "b@x.com", datetime(2026, 5, 12, tzinfo=timezone.utc)),
            3: _fetch_row("undated", "c@x.com", None, internaldate=False),
        }
    }
    metas = list(_reader().scan_metadata(since=datetime(2026, 5, 5, tzinfo=timezone.utc)))

    # 'old' is before the watermark; 'undated' has no date to place against it.
    assert {m.subject for m in metas} == {"new"}


def test_scan_metadata_folder_allowlist() -> None:
    FakeIMAPClient.FOLDERS = {
        "INBOX": {1: _fetch_row("keep", "a@x.com", datetime(2026, 5, 10, tzinfo=timezone.utc))},
        "[Gmail]/All Mail": {2: _fetch_row("skip", "b@x.com", datetime(2026, 5, 10, tzinfo=timezone.utc))},
    }
    metas = list(_reader(folders=["INBOX"]).scan_metadata())
    assert {m.subject for m in metas} == {"keep"}


def test_scan_metadata_graceful_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset password env var → warning logged, scan yields nothing, no crash."""
    monkeypatch.delenv("TEST_IMAP_PASS", raising=False)
    FakeIMAPClient.FOLDERS = {"INBOX": {1: _fetch_row("x", "a@x.com", datetime(2026, 5, 10, tzinfo=timezone.utc))}}
    assert list(_reader().scan_metadata()) == []


def test_scan_metadata_graceful_on_login_failure() -> None:
    """Bad app password → IMAP login raises → caught, yields nothing."""
    FakeIMAPClient.RAISE_ON_LOGIN = True
    FakeIMAPClient.FOLDERS = {"INBOX": {1: _fetch_row("x", "a@x.com", datetime(2026, 5, 10, tzinfo=timezone.utc))}}
    assert list(_reader().scan_metadata()) == []


# ── resolve_reader dispatch ──────────────────────────────────────────


def test_resolve_reader_dispatches_imap_kind() -> None:
    reader = resolve_reader(
        {
            "email": "alex@example.com",
            "reader": {
                "kind": "imap",
                "imap_host": "imap.gmail.com",
                "imap_pass_env": "TEST_IMAP_PASS",
            },
        }
    )
    assert isinstance(reader, ImapReader)
    # imap_user_env unset → user falls back to account.email.
    assert reader._default_user == "alex@example.com"
    assert reader._host == "imap.gmail.com"
