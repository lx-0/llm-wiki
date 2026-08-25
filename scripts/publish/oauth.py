"""Producer OAuth flow against context-mcp's authorization server (M030-S02-T06).

Why this exists: the wiki write tools are USER-principal only — the Keychain
org api-key from MCP-CONNECT.md is read-only, and user access-JWTs are
short-lived. The producer therefore does ONE interactive browser consent
(public client, DCR, PKCE S256, scope ``offline_access``) and afterwards
refreshes headlessly; the refresh-issuance condition (client allows the
refresh grant AND scope offline_access) was verified in the vendored
better-auth oauth-provider. Token cache follows the google_oauth convention:
``STATE_DIR/meinkontext-oauth.json`` via the locked StateStore.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

import httpx

from publish.client import PublishClientError

from core.paths import STATE_DIR
from core.state_store import StateStore

DEFAULT_TOKEN_PATH = STATE_DIR / "meinkontext-oauth.json"
_SKEW_S = 60
_AUTH_HINT = "run `wiki publish --auth` to (re)connect the producer"


def token_store(path: Path | None = None) -> StateStore:
    return StateStore(path or DEFAULT_TOKEN_PATH)


def _get_json(http: httpx.Client, url: str) -> dict:
    try:
        response = http.get(url)
    except httpx.HTTPError as exc:
        raise PublishClientError(f"{url}: {exc}") from exc
    if response.status_code != 200:
        raise PublishClientError(f"{url}: HTTP {response.status_code}")
    return response.json()


def discover(http: httpx.Client, endpoint: str) -> dict:
    """RFC 9728 protected-resource metadata → RFC 8414 AS metadata."""
    parsed = urllib.parse.urlparse(endpoint)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    resource_meta = _get_json(
        http, f"{origin}/.well-known/oauth-protected-resource{parsed.path}"
    )
    servers = resource_meta.get("authorization_servers") or []
    if not servers:
        raise PublishClientError(f"{endpoint}: no authorization_servers in metadata")
    as_url = servers[0].rstrip("/")
    as_parsed = urllib.parse.urlparse(as_url)
    candidates = [
        # better-auth mounts the RFC 8414 path-insertion form
        f"{as_parsed.scheme}://{as_parsed.netloc}"
        f"/.well-known/oauth-authorization-server{as_parsed.path}",
        f"{as_url}/.well-known/oauth-authorization-server",
    ]
    last: Exception | None = None
    for candidate in candidates:
        try:
            return _get_json(http, candidate)
        except PublishClientError as exc:
            last = exc
    raise PublishClientError(f"AS metadata discovery failed: {last}")


def _register_client(http: httpx.Client, meta: dict, redirect_uri: str) -> str:
    payload = {
        "client_name": "llm-wiki publish",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "offline_access",
    }
    try:
        response = http.post(meta["registration_endpoint"], json=payload)
    except httpx.HTTPError as exc:
        raise PublishClientError(f"client registration failed: {exc}") from exc
    if response.status_code not in (200, 201):
        raise PublishClientError(
            f"client registration failed: HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )
    return response.json()["client_id"]


def _wait_for_code(timeout_s: int = 300, _start_only: bool = False):
    """Loopback listener: returns ``(port, result)`` — ``result()`` blocks for
    one request and hands back the ``code`` query param."""
    holder: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            holder["code"] = query.get("code")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"llm-wiki publish connected - you can close this tab.")

        def log_message(self, *args: object) -> None:  # silence stdout
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]

    def run() -> None:
        try:
            server.handle_request()
        finally:
            server.server_close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def result() -> str:
        thread.join(timeout_s)
        code = holder.get("code")
        if not code:
            raise PublishClientError(
                "no authorization code received (consent timed out or was denied)"
            )
        return code

    return port, result


def _exchange(http: httpx.Client, token_endpoint: str, form: dict) -> dict:
    try:
        response = http.post(token_endpoint, data=form)
    except httpx.HTTPError as exc:
        raise PublishClientError(f"token request failed: {exc}") from exc
    if response.status_code != 200:
        raise PublishClientError(
            f"token request failed: HTTP {response.status_code}: {response.text[:200]}"
        )
    return response.json()


def _persist(store: StateStore, tokens: dict, extra: dict) -> None:
    def _mut(data: dict) -> None:
        data.update(extra)
        data["access_token"] = tokens["access_token"]
        data["expires_at"] = time.time() + float(tokens.get("expires_in", 300))
        if tokens.get("refresh_token"):
            data["refresh_token"] = tokens["refresh_token"]

    store.update(_mut)


def mint_interactive(
    endpoint: str,
    store_path: Path | None = None,
    *,
    http: httpx.Client | None = None,
    consent: Callable[[str], str] | None = None,
    timeout_s: int = 300,
) -> None:
    """One-time producer connect: discovery → DCR → browser consent → tokens.

    ``consent`` (tests) receives the authorize URL and returns the code; the
    real flow starts the loopback listener and opens the browser.
    """
    http = http or httpx.Client(timeout=httpx.Timeout(10.0))
    meta = discover(http, endpoint)

    wait: Callable[[], str] | None = None
    if consent is None:
        port, wait = _wait_for_code(timeout_s)
        redirect_uri = f"http://127.0.0.1:{port}/callback"
    else:
        redirect_uri = "http://127.0.0.1:0/callback"

    client_id = _register_client(http, meta, redirect_uri)

    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    auth_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": endpoint,
        "state": secrets.token_urlsafe(16),
    })

    if consent is not None:
        code = consent(auth_url)
    else:
        print(f"Open in your browser (login + consent):\n\n  {auth_url}\n")
        webbrowser.open(auth_url)
        assert wait is not None
        code = wait()

    tokens = _exchange(http, meta["token_endpoint"], {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": endpoint,
    })
    _persist(token_store(store_path), tokens, {
        "client_id": client_id,
        "token_endpoint": meta["token_endpoint"],
        "resource": endpoint,
    })


def current_access_token(
    store_path: Path | None = None,
    *,
    http: httpx.Client | None = None,
    force_refresh: bool = False,
) -> str:
    """A valid access token from the cache — refreshed (with rotation) when
    stale, or unconditionally with ``force_refresh`` (the client forces one
    after a mid-run -32001: server-side expiry beats our local clock).
    Raises with an actionable ``--auth`` hint when disconnected."""
    store = token_store(store_path)
    data = store.reload()
    if not data.get("refresh_token"):
        raise PublishClientError(f"no producer token — {_AUTH_HINT}")
    if (
        not force_refresh
        and data.get("access_token")
        and data.get("expires_at", 0) > time.time() + _SKEW_S
    ):
        return data["access_token"]

    http = http or httpx.Client(timeout=httpx.Timeout(10.0))
    try:
        tokens = _exchange(http, data["token_endpoint"], {
            "grant_type": "refresh_token",
            "refresh_token": data["refresh_token"],
            "client_id": data["client_id"],
            "resource": data.get("resource", ""),
        })
    except PublishClientError as exc:
        raise PublishClientError(f"token refresh failed ({exc}) — {_AUTH_HINT}") from exc
    _persist(store, tokens, {})
    return tokens["access_token"]
