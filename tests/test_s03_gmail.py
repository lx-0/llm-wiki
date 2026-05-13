"""S03 — GmailReader resolves; OAuth bootstrap fails clearly when client_secret missing."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.mailbox import resolve_reader, resolve_filter, MailboxReader, MailboxFilter
from adapters.mailbox.gmail import GmailFilter, GmailReader


def test_resolve_reader_gmail_api_returns_reader() -> None:
    account = {
        "_id": "private",
        "email": "y@gmail.com",
        "reader": {"kind": "gmail-api"},
    }
    r = resolve_reader(account)
    assert r is not None
    assert isinstance(r, MailboxReader)
    assert isinstance(r, GmailReader)


def test_resolve_filter_gmail_api_returns_filter() -> None:
    account = {
        "_id": "private",
        "email": "y@gmail.com",
        "filter": {"kind": "gmail-api"},
    }
    f = resolve_filter(account)
    assert f is not None
    assert isinstance(f, MailboxFilter)
    assert isinstance(f, GmailFilter)


def test_gmail_auth_bootstrap_missing_client_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an OAuth client_secret.json, bootstrap fails clearly without crashing."""
    from adapters.mailbox import gmail as gmail_mod

    # Point the OAuth client path at a non-existent location.
    monkeypatch.setattr(gmail_mod, "_OAUTH_CLIENT", tmp_path / "definitely-not-here.json")
    ok, msg = gmail_mod.gmail_auth_bootstrap("test")
    assert not ok
    assert "Missing OAuth client config" in msg
    assert "console.cloud.google.com" in msg


def test_token_path_under_state_dir() -> None:
    from adapters.mailbox.gmail import _token_path
    from core.config import STATE_DIR

    p = _token_path("private")
    assert p.parent == STATE_DIR
    assert p.name == "gmail-token-private.json"
