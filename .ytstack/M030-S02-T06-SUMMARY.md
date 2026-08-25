---
milestone: M030
slice: S02
task: T06
project: llm-wiki
closed: 2026-08-25T13:00:00Z
verification: passed
---

# M030-S02-T06 -- Summary

## Commits

- `feat(publish): OAuth producer flow — one consent, headless refresh (M030-S02-T06)` (committed with this summary)

## Outcome

`scripts/publish/oauth.py`: `wiki publish --auth` runs discovery (RFC 9728 protected-resource → RFC 8414 AS metadata, better-auth path-insertion form first), DCR as public client (`grant_types [authorization_code, refresh_token]`, auth method none), PKCE S256, loopback listener, one browser consent with `scope=offline_access` + `resource=<endpoint>`, token exchange; tokens persist at `STATE_DIR/meinkontext-oauth.json` (google_oauth cache convention, locked StateStore). `current_access_token` serves fresh tokens without network and refreshes with rotation when stale; refresh failure and missing store answer with the `--auth` hint. Live path resolves: `MEINKONTEXT_TOKEN` env (explicit USER-token override) → OAuth store. `resolve_token` (the wrong static-token design) removed; .env template + M030-CONTEXT corrected.

Root cause this task fixes (operator catch): upstream documents no producer-token mint — MCP-CONNECT.md's Keychain token is an org api-key (read-only for write tools), user JWTs are short-lived. Refresh-issuance condition (client allows refresh grant AND scope offline_access) verified in the vendored @better-auth/oauth-provider 1.7.0-rc.1.

## Deviations from plan

None (task itself was the deviation-fix).

## Follow-ups

- T05 live run now: `wiki config set publish.endpoint …` → `wiki publish --auth` (browser) → `--dry-run` review → `wiki publish`. First empirical proof that the dev server issues refresh tokens to DCR clients — if it refuses `offline_access`/refresh for public clients, that becomes an upstream ask (REGEL #2, operator tasking).

## Verification

Command: `uv run pytest tests/test_publish_oauth.py tests/test_publish_cli.py -q` (10 passed) + `uv run pytest -q` (1842 passed, 1 pre-existing skip) -- passed.
