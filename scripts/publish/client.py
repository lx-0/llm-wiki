"""Stateless MCP JSON-RPC client for the meinkontext producer (M030-S02-T01).

The server (context-mcp) runs Streamable HTTP with ``enableJsonResponse`` —
every request is a plain ``POST <endpoint>`` JSON round-trip, no SSE parsing,
no session id (verified live 2026-08-25: unauthenticated initialize answers
HTTP 401 with a JSON-RPC error body and OAuth resource metadata in
``www-authenticate``). No MCP SDK dependency needed.

Timeouts follow the house httpx pattern: explicit ``httpx.Timeout`` on every
axis — a read timeout alone does not fire on half-open sockets.
"""
from __future__ import annotations

import itertools
import os

import httpx

PROTOCOL_VERSION = "2025-06-18"
_RUNBOOK_HINT = (
    "mint a user-scoped OAuth token per context-mcp's live-import runbook "
    "(docs/setup/MCP-CONNECT.md) and export it as MEINKONTEXT_TOKEN in "
    "<vault>/.claude/.env"
)


class PublishClientError(RuntimeError):
    """Transport-level failure: HTTP status, JSON-RPC error, malformed body."""


class ToolCallError(RuntimeError):
    """The tool executed and answered ``isError: true`` (e.g. secret-gate
    reject, cross-wiki slug conflict). Message = the tool's text content."""


def resolve_token() -> str:
    token = os.environ.get("MEINKONTEXT_TOKEN", "").strip()
    if not token:
        raise PublishClientError(f"MEINKONTEXT_TOKEN is not set — {_RUNBOOK_HINT}")
    return token


def tool_text(result: dict) -> str:
    """First text content block of an MCP tool result (empty if none)."""
    for block in result.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


class ContextMcpClient:
    """One authenticated producer connection: lazy initialize handshake, then
    ``tools/call`` round-trips. Publish is sequential by contract — one client,
    one request at a time."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        timeout: httpx.Timeout | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not endpoint:
            raise PublishClientError(
                "publish.endpoint is not configured (wiki config set publish.endpoint …)"
            )
        self._endpoint = endpoint
        self._ids = itertools.count(1)
        self._protocol: str | None = None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }
        self._http = httpx.Client(
            headers=headers,
            timeout=timeout
            or httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
            transport=transport,
        )

    # ── wire ────────────────────────────────────────────────────────────

    def _post(self, payload: dict) -> httpx.Response:
        headers = {}
        if self._protocol:
            headers["MCP-Protocol-Version"] = self._protocol
        try:
            return self._http.post(self._endpoint, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise PublishClientError(f"{self._endpoint}: {exc}") from exc

    def _rpc(self, method: str, params: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": method,
            "params": params,
        }
        response = self._post(payload)
        body: dict = {}
        try:
            body = response.json()
        except ValueError:
            pass
        error = body.get("error")
        if error:
            raise PublishClientError(
                f"{method}: server error {error.get('code')}: {error.get('message')}"
            )
        if response.status_code != 200:
            raise PublishClientError(
                f"{method}: HTTP {response.status_code}: {response.text[:200]}"
            )
        if "result" not in body:
            raise PublishClientError(f"{method}: malformed response (no result)")
        return body["result"]

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def _ensure_initialized(self) -> None:
        if self._protocol is not None:
            return
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "llm-wiki-publish", "version": "1.0"},
            },
        )
        self._protocol = result.get("protocolVersion", PROTOCOL_VERSION)
        self._notify("notifications/initialized")

    # ── surface ─────────────────────────────────────────────────────────

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Run one tool; returns the MCP result object. ``isError: true``
        raises ``ToolCallError`` with the tool's text."""
        self._ensure_initialized()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise ToolCallError(tool_text(result) or f"{name}: tool error")
        return result

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ContextMcpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
