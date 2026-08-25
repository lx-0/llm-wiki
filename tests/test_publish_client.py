"""Tests for the stateless MCP JSON-RPC client (M030-S02-T01).

Wire shape verified live against dev.meinkontext.de (2026-08-25): the server
runs Streamable HTTP with enableJsonResponse — plain JSON round-trips; an
unauthenticated call answers HTTP 401 with a JSON-RPC error body
(code -32001). Tests drive the real client through httpx.MockTransport.
"""
from __future__ import annotations

import json

import httpx
import pytest

from publish.client import (
    ContextMcpClient,
    PublishClientError,
    ToolCallError,
    tool_text,
)


def _server(recorder: list[dict], responder=None):
    """MockTransport speaking the observed wire shape."""

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode()) if request.content else {}
        recorder.append({"headers": dict(request.headers), "payload": payload})
        method = payload.get("method")
        if responder is not None:
            custom = responder(method, payload)
            if custom is not None:
                return custom
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {"protocolVersion": "2025-06-18",
                           "serverInfo": {"name": "context-mcp", "version": "0.0.56"},
                           "capabilities": {}},
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {"content": [{"type": "text", "text": '{"ok": true}'}],
                           "isError": False},
            })
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload.get("id"), "result": {}})

    return httpx.MockTransport(handle)


def _client(recorder: list[dict], responder=None) -> ContextMcpClient:
    return ContextMcpClient(
        "https://example.test/mcp", "tok-123",
        transport=_server(recorder, responder),
    )


def test_call_tool_initializes_once_and_sends_bearer() -> None:
    seen: list[dict] = []
    client = _client(seen)
    client.call_tool("list_wikis", {})
    client.call_tool("list_wikis", {})
    methods = [s["payload"].get("method") for s in seen]
    assert methods == ["initialize", "notifications/initialized", "tools/call", "tools/call"]
    assert all(s["headers"]["authorization"] == "Bearer tok-123" for s in seen)
    # after the handshake, calls carry the negotiated protocol version
    assert seen[2]["headers"]["mcp-protocol-version"] == "2025-06-18"


def test_call_tool_returns_result_and_tool_text_parses() -> None:
    seen: list[dict] = []
    result = _client(seen).call_tool("list_wikis", {})
    assert result["isError"] is False
    assert json.loads(tool_text(result)) == {"ok": True}


def test_http_401_raises_publish_client_error() -> None:
    def responder(method, payload):
        return httpx.Response(401, json={
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": "Unauthorized"}, "id": None,
        })

    with pytest.raises(PublishClientError, match="Unauthorized"):
        _client([], responder).call_tool("list_wikis", {})


def test_jsonrpc_error_raises_publish_client_error() -> None:
    def responder(method, payload):
        if method == "tools/call":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32602, "message": "unknown tool"},
            })
        return None

    with pytest.raises(PublishClientError, match="unknown tool"):
        _client([], responder).call_tool("nope", {})


def test_tool_is_error_raises_tool_call_error_with_text() -> None:
    def responder(method, payload):
        if method == "tools/call":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "result": {"content": [{"type": "text",
                                        "text": "secret-shaped value detected"}],
                           "isError": True},
            })
        return None

    with pytest.raises(ToolCallError, match="secret-shaped"):
        _client([], responder).call_tool("write_article", {"wiki": "w"})


def test_publish_config_block_defaults() -> None:
    from core.config_schema import Publish

    p = Publish()
    assert p.enabled is False
    assert p.endpoint == ""
    assert p.wiki_slug == "llm-wiki"
    assert p.wiki_name == "LLM Wiki"
