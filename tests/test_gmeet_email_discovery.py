"""M024 — gmeet email-discovery: resolver defaults + the `_discover_via_email`
producer (fake reader + fake Drive client, no network)."""

from __future__ import annotations

import types

import pytest

from collectors import gmeet


def _fake_config(accounts: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        personal=types.SimpleNamespace(accounts=accounts),
        limits=types.SimpleNamespace(gmeet_max_per_run=50, gmeet_request_timeout_s=30),
    )


# ── resolver ─────────────────────────────────────────────────────────


def test_resolver_email_discovery_defaults(monkeypatch) -> None:
    accounts = {"work": {"gmeet": {"kind": "gmeet-api"}}}
    monkeypatch.setattr(gmeet, "CONFIG", _fake_config(accounts))
    [acct] = gmeet._resolve_gmeet_accounts()
    assert acct.email_discovery is True
    assert acct.email_senders == ("gemini-notes@google.com",)
    assert acct.email_folder == "INBOX"
    assert acct.email_backfill_days == 30


def test_resolver_email_discovery_explicit_overrides(monkeypatch) -> None:
    accounts = {
        "work": {
            "gmeet": {
                "kind": "gmeet-api",
                "email_discovery": {
                    "enabled": False,
                    "senders": ["a@b.de", "c@d.de"],
                    "folder": "INBOX/Meetings",
                    "backfill_days": 7,
                },
            }
        }
    }
    monkeypatch.setattr(gmeet, "CONFIG", _fake_config(accounts))
    [acct] = gmeet._resolve_gmeet_accounts()
    assert acct.email_discovery is False
    assert acct.email_senders == ("a@b.de", "c@d.de")
    assert acct.email_folder == "INBOX/Meetings"
    assert acct.email_backfill_days == 7


# ── producer ─────────────────────────────────────────────────────────


def _msg(from_addr: str, html: str = "", text: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        meta=types.SimpleNamespace(from_addr=from_addr),
        body_html=html,
        body_text=text,
    )


class _FakeReader:
    def __init__(self, messages: list) -> None:
        self._messages = messages
        self.scanned_folder: str | None = None

    def scan_deep(self, folder, limit=0, since=None):  # noqa: ANN001
        self.scanned_folder = folder
        yield from self._messages


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _get(self, url, params=None):  # noqa: ANN001
        self.calls.append(url)
        doc_id = url.rsplit("/", 1)[-1]
        return {
            "id": doc_id,
            "name": f"Sync {doc_id} – Notizen von Gemini",
            "createdTime": "2026-05-21T10:00:00Z",
            "webViewLink": f"https://docs.google.com/document/d/{doc_id}/edit",
        }


def _acct(**over) -> gmeet._GmeetAccount:
    base = dict(
        account_id="work",
        drive_folder_id="",
        drive_folder_name="Meet Recordings",
        since=None,
        max_per_run=50,
        email_discovery=True,
        email_senders=("gemini-notes@google.com",),
        email_folder="INBOX",
        email_backfill_days=30,
    )
    base.update(over)
    return gmeet._GmeetAccount(**base)


_HTML = '<a href="https://docs.google.com/document/d/DOCAAA/edit?usp=meet_tnfm_email">x</a>'


@pytest.fixture
def _collector(monkeypatch):
    monkeypatch.setattr(gmeet, "CONFIG", _fake_config({"work": {"reader": {"kind": "fake"}}}))
    return gmeet.GmeetCollector()


def test_discover_via_email_ingests_colleague_doc(monkeypatch, _collector) -> None:
    reader = _FakeReader([_msg("Gemini <gemini-notes@google.com>", html=_HTML)])
    monkeypatch.setattr(gmeet, "resolve_reader", lambda body: reader)
    client = _FakeClient()
    stubs, note = _collector._discover_via_email(_acct(), client, set())
    assert reader.scanned_folder == "INBOX"
    assert [s["id"] for s in stubs] == ["DOCAAA"]
    assert client.calls and client.calls[0].endswith("/files/DOCAAA")
    assert "1 linked / 1 new" in note


def test_discover_via_email_dedups_already_present(monkeypatch, _collector) -> None:
    reader = _FakeReader([_msg("Gemini <gemini-notes@google.com>", html=_HTML)])
    monkeypatch.setattr(gmeet, "resolve_reader", lambda body: reader)
    client = _FakeClient()
    already = {gmeet._short_id("DOCAAA")}
    stubs, note = _collector._discover_via_email(_acct(), client, already)
    assert stubs == []
    assert client.calls == []  # dedup avoids the files.get
    assert "1 linked / 0 new" in note


def test_discover_via_email_filters_by_sender(monkeypatch, _collector) -> None:
    reader = _FakeReader([_msg("Someone <other@elsewhere.com>", html=_HTML)])
    monkeypatch.setattr(gmeet, "resolve_reader", lambda body: reader)
    stubs, note = _collector._discover_via_email(_acct(), _FakeClient(), set())
    assert stubs == []
    assert "0 linked" in note


def test_discover_via_email_disabled_is_noop(monkeypatch, _collector) -> None:
    stubs, note = _collector._discover_via_email(_acct(email_discovery=False), _FakeClient(), set())
    assert stubs == [] and note == ""


def test_discover_via_email_no_reader_degrades(monkeypatch, _collector) -> None:
    monkeypatch.setattr(gmeet, "resolve_reader", lambda body: None)
    stubs, note = _collector._discover_via_email(_acct(), _FakeClient(), set())
    assert stubs == []
    assert "no reader" in note


def test_discover_via_email_reader_error_degrades(monkeypatch, _collector) -> None:
    class _Boom:
        def scan_deep(self, folder, limit=0, since=None):  # noqa: ANN001
            raise gmeet.MailboxReadError("mbox gone")

    monkeypatch.setattr(gmeet, "resolve_reader", lambda body: _Boom())
    stubs, note = _collector._discover_via_email(_acct(), _FakeClient(), set())
    assert stubs == []
    assert "email-scan failed" in note
