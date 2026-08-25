"""Tests for the producer OAuth flow (M030-S02-T06).

Write tools are user-principal only; the user JWT is short-lived. The
producer therefore holds a refresh token (scope `offline_access`, PKCE
public client) and refreshes headlessly — one browser consent at setup.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import httpx
import pytest

from publish.client import PublishClientError
from publish.oauth import (
    current_access_token,
    mint_interactive,
    token_store,
    _wait_for_code,
)

ORIGIN = "https://mk.test"
ENDPOINT = f"{ORIGIN}/mcp"


def _as_transport(recorder: list[dict], *, expires_in: int = 300):
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = request.content.decode() if request.content else ""
        recorder.append({"url": url, "body": body})
        if url.endswith("/.well-known/oauth-protected-resource/mcp"):
            return httpx.Response(200, json={
                "resource": ENDPOINT,
                "authorization_servers": [f"{ORIGIN}/api/auth"],
            })
        if "/.well-known/oauth-authorization-server" in url:
            return httpx.Response(200, json={
                "issuer": f"{ORIGIN}/api/auth",
                "authorization_endpoint": f"{ORIGIN}/api/auth/oauth2/authorize",
                "token_endpoint": f"{ORIGIN}/api/auth/oauth2/token",
                "registration_endpoint": f"{ORIGIN}/api/auth/oauth2/register",
            })
        if url.endswith("/oauth2/register"):
            payload = json.loads(body)
            assert "refresh_token" in payload["grant_types"]
            assert payload["token_endpoint_auth_method"] == "none"
            return httpx.Response(201, json={"client_id": "client-1"})
        if url.endswith("/oauth2/token"):
            form = dict(urllib.parse.parse_qsl(body))
            if form["grant_type"] == "authorization_code":
                assert form["code"] == "code-abc"
                assert form["code_verifier"]
                return httpx.Response(200, json={
                    "access_token": "acc-1", "expires_in": expires_in,
                    "refresh_token": "ref-1", "token_type": "Bearer",
                })
            assert form["grant_type"] == "refresh_token"
            if form["refresh_token"] == "ref-1":
                return httpx.Response(200, json={
                    "access_token": "acc-2", "expires_in": expires_in,
                    "refresh_token": "ref-2", "token_type": "Bearer",
                })
            return httpx.Response(400, json={"error": "invalid_grant"})
        raise AssertionError(f"unexpected url {url}")

    return httpx.MockTransport(handle)


def _mint(tmp_path: Path, recorder: list[dict], *, expires_in: int = 300) -> Path:
    store_path = tmp_path / "meinkontext-oauth.json"
    opened: list[str] = []

    def fake_consent(auth_url: str) -> str:
        opened.append(auth_url)
        return "code-abc"

    http = httpx.Client(transport=_as_transport(recorder, expires_in=expires_in))
    mint_interactive(ENDPOINT, store_path, http=http, consent=fake_consent)
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(opened[0]).query))
    assert q["scope"] == "offline_access"
    assert q["code_challenge_method"] == "S256"
    assert q["resource"] == ENDPOINT
    assert q["client_id"] == "client-1"
    return store_path


def test_mint_persists_tokens_and_pkce_consent(tmp_path: Path) -> None:
    recorder: list[dict] = []
    store_path = _mint(tmp_path, recorder)
    data = token_store(store_path).load()
    assert data["access_token"] == "acc-1"
    assert data["refresh_token"] == "ref-1"
    assert data["client_id"] == "client-1"
    assert data["expires_at"] > 0


def test_current_token_returns_fresh_without_network(tmp_path: Path) -> None:
    recorder: list[dict] = []
    store_path = _mint(tmp_path, recorder)
    before = len(recorder)
    http = httpx.Client(transport=_as_transport(recorder))
    assert current_access_token(store_path, http=http) == "acc-1"
    assert len(recorder) == before  # no HTTP for a still-valid token


def test_current_token_refreshes_and_rotates(tmp_path: Path) -> None:
    recorder: list[dict] = []
    store_path = _mint(tmp_path, recorder, expires_in=1)  # immediately stale
    http = httpx.Client(transport=_as_transport(recorder))
    assert current_access_token(store_path, http=http) == "acc-2"
    data = token_store(store_path).load()
    assert data["refresh_token"] == "ref-2"  # rotation persisted


def test_refresh_failure_points_at_auth(tmp_path: Path) -> None:
    recorder: list[dict] = []
    store_path = _mint(tmp_path, recorder, expires_in=1)
    store = token_store(store_path)
    store.update(lambda d: d.update(refresh_token="ref-dead"))
    http = httpx.Client(transport=_as_transport(recorder))
    with pytest.raises(PublishClientError, match="--auth"):
        current_access_token(store_path, http=http)


def test_missing_store_points_at_auth(tmp_path: Path) -> None:
    with pytest.raises(PublishClientError, match="--auth"):
        current_access_token(tmp_path / "absent.json", http=httpx.Client(
            transport=_as_transport([])))


def test_wait_for_code_loopback_listener() -> None:
    port, result = _wait_for_code(timeout_s=5, _start_only=True)
    try:
        url = f"http://127.0.0.1:{port}/callback?code=code-xyz&state=st"

        def hit() -> None:
            urllib.request.urlopen(url, timeout=3).read()

        t = threading.Thread(target=hit)
        t.start()
        code = result()
        t.join()
        assert code == "code-xyz"
    finally:
        pass
