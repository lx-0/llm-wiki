"""ollama_client records token usage into the ledger (no live server)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Stand-in for the httpx.Client returned by ollama_client._client().

    Call sites now do `with _client(timeout) as c: c.post(...)` so the
    TCP-keepalive transport + explicit phase timeouts apply uniformly; tests
    patch `_client` rather than the module-level `httpx.post`."""

    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *a, **k):
        return self._resp

    def get(self, *a, **k):
        return self._resp


def test_chat_records_openai_usage(monkeypatch):
    from core import ollama_client, usage
    fresh = usage.UsageLedger()
    monkeypatch.setattr(ollama_client, "LEDGER", fresh)
    monkeypatch.setattr(ollama_client, "_client", lambda timeout: _FakeClient(_FakeResp(
        {"choices": [{"message": {"content": " hi "}}],
         "usage": {"prompt_tokens": 11, "completion_tokens": 3}})))
    out = ollama_client.chat("p", model="gemma4:e4b")
    assert out == "hi"
    u = fresh.totals()[("ollama", "gemma4:e4b")]
    assert (u.input_tokens, u.output_tokens, u.calls) == (11, 3, 1)


def test_chat_schema_records_native_counts(monkeypatch):
    from core import ollama_client, usage
    fresh = usage.UsageLedger()
    monkeypatch.setattr(ollama_client, "LEDGER", fresh)
    monkeypatch.setattr(ollama_client, "_client", lambda timeout: _FakeClient(_FakeResp(
        {"message": {"content": "{}"}, "prompt_eval_count": 20, "eval_count": 8})))
    ollama_client.chat_schema("p", model="gemma4:e4b", schema={})
    u = fresh.totals()[("ollama", "gemma4:e4b")]
    assert (u.input_tokens, u.output_tokens) == (20, 8)


def test_chat_vision_records_stats(monkeypatch):
    from core import ollama_client, usage
    fresh = usage.UsageLedger()
    monkeypatch.setattr(ollama_client, "LEDGER", fresh)
    monkeypatch.setattr(ollama_client, "_client", lambda timeout: _FakeClient(_FakeResp(
        {"message": {"content": "desc"}, "prompt_eval_count": 5, "eval_count": 2})))
    content, stats = ollama_client.chat_vision("p", model="vision:x", image_b64="x")
    assert content == "desc" and stats["eval_count"] == 2
    assert fresh.totals()[("ollama", "vision:x")].output_tokens == 2
