---
milestone: M030
slice: S02
task: T01
project: llm-wiki
closed: 2026-08-25T10:40:00Z
verification: passed
---

# M030-S02-T01 -- Summary

## Commits

- `feat(publish): stateless MCP JSON-RPC client + publish.* knobs + httpx declared (M030-S02-T01)` (committed with this summary)

## Outcome

`scripts/publish/client.py`: `ContextMcpClient` speaks plain JSON-RPC over `POST <endpoint>` (server's `enableJsonResponse` verified LIVE — unauthenticated initialize against dev.meinkontext.de answered HTTP 401 with a JSON-RPC error body + OAuth resource metadata). Lazy initialize handshake + `notifications/initialized`, negotiated `MCP-Protocol-Version` header on subsequent calls, bearer auth, explicit `httpx.Timeout` on all four axes, injectable transport (tests use MockTransport against the observed wire shape). Error ladder: HTTP/JSON-RPC failures → `PublishClientError`; tool `isError: true` → `ToolCallError` with the tool's text. `resolve_token()` reads `MEINKONTEXT_TOKEN` with a runbook-pointing error. Config: new `Publish` block (enabled=False, endpoint="", wiki_slug/wiki_name) in schema + example.yaml + migration policy (`INJECTED_KEYS["publish"]`, section tuple extended — migrate_additions creates new parent blocks). `httpx` finally declared in pyproject.

## Deviations from plan

One found-and-fixed defect beyond plan scope: `config_docs.py` enumerates sections via a hand-maintained `_SECTIONS` tuple and reported "docs already current" while silently omitting the new block — added `("publish", Publish)` and regenerated docs/config.md. Silent-skip class noted for KNOWLEDGE.md at slice close.

## Follow-ups

- KNOWLEDGE.md entry: three hand-maintained section registries must be touched for a NEW top-level config block (config_schema WikiConfig, migration section tuple, config_docs `_SECTIONS`) — the docs one fails SILENT.

## Verification

Command: `uv run pytest tests/test_publish_client.py tests/test_migrate_config_keys.py -q` (51 passed) + `uv run pytest -q` (1825 passed, 1 pre-existing skip) -- passed.
