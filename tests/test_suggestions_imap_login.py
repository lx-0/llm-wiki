"""`suggestions/backends/imap.py:_imap_client` — the IMAP login behind the suggestions'
retroactive actions (`imap-move` / `imap-tag` / `imap-set-flags`).

A Gmail account logs in with OAuth2 (XOAUTH2) on the gmail adapter's credentials. Since
74f3d84 (2026-05-14, the OAuth dance moved into `core/google_oauth.py`) the import named a
`_credentials` the adapter no longer defined; a mypy-coded `type: ignore` hid it from
pyright, ty's probe found it (M033-S05-T01). A password account logs in with its env vars.
"""

from __future__ import annotations

import sys
import types

import pytest

from suggestions.backends import imap as imap_actions


class _FakeIMAPClient:
    def __init__(self, host: str, ssl: bool = True) -> None:
        self.host = host
        self.logins: list[tuple[str, str, str]] = []

    def oauth2_login(self, user: str, token: str) -> None:
        self.logins.append(("oauth2", user, token))

    def login(self, user: str, passwd: str) -> None:
        self.logins.append(("login", user, passwd))


def _account(**reader: str) -> dict:
    return {"email": "op@example.com", "reader": dict(reader)}


@pytest.fixture
def imap_env(monkeypatch):
    """A fake `imapclient` module and a CONFIG with one Gmail + one password account."""
    fake = types.ModuleType("imapclient")
    fake.IMAPClient = _FakeIMAPClient
    monkeypatch.setitem(sys.modules, "imapclient", fake)
    accounts = {
        "gm": _account(kind="gmail-api", imap_host="imap.gmail.com"),
        "pw": _account(imap_host="mail.example.com", imap_user_env="U_ENV", imap_pass_env="P_ENV"),
    }
    monkeypatch.setattr(
        imap_actions,
        "CONFIG",
        types.SimpleNamespace(personal=types.SimpleNamespace(accounts=accounts)),
    )
    return monkeypatch


def test_gmail_account_logs_in_with_the_oauth_token(imap_env) -> None:
    from core import google_oauth

    imap_env.setattr(
        google_oauth,
        "credentials",
        lambda app, account_id: (types.SimpleNamespace(token=f"tok-{account_id}"), None),
    )
    client, err = imap_actions._imap_client("gm")
    assert err is None
    assert client.logins == [("oauth2", "op@example.com", "tok-gm")]


def test_gmail_account_without_a_token_returns_the_hint(imap_env) -> None:
    from core import google_oauth

    imap_env.setattr(
        google_oauth, "credentials", lambda app, account_id: (None, "run wiki gmail-auth")
    )
    assert imap_actions._imap_client("gm") == (None, "run wiki gmail-auth")


def test_password_account_logs_in_with_its_env_vars(imap_env) -> None:
    imap_env.setenv("U_ENV", "user")
    imap_env.setenv("P_ENV", "secret")
    client, err = imap_actions._imap_client("pw")
    assert err is None
    assert client.logins == [("login", "user", "secret")]
