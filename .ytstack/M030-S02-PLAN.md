---
milestone: M030
slice: S02
project: llm-wiki
created: 2026-08-25T07:01:45Z
status: planned
task_count: 5
completed_tasks: 4
---

# M030-S02 -- Slice Plan

**Goal:** `wiki publish` executes the S01 plan against meinkontext per `docs/PRODUCER-CONTRACT.md` — wiki bootstrap, sequential writes, retraction/restore, fail-soft error posture — proven by a first full live publish of the operator vault.

## Tasks

- [x] T01 -- Minimal stateless MCP JSON-RPC client over httpx (`initialize` + `tools/call` against `POST /mcp`; the server runs Streamable HTTP with `enableJsonResponse: true`, so plain JSON round-trips suffice — no new SDK dependency): bearer token from `MEINKONTEXT_TOKEN` in `<vault>/.claude/.env` (their client convention), explicit `httpx.Timeout` + keepalive per house pattern; **declare `httpx` in `pyproject.toml` in the SAME commit** (engine-wide latent violation of the deps-explicit rule — it is imported everywhere but never declared). Config knobs `publish.enabled` (default false), `publish.endpoint`, `publish.wiki_slug`, `publish.wiki_name` in `config_schema.py` + `config.example.yaml` + migration entries in the SAME commit. The token is NO schema key at all — .env-only (llm-wiki's own `.env` convention, like EXA/IMAP), so no migration class applies.
- [x] T02 -- Wiki bootstrap: idempotent `create_wiki {name, slug, managed_by: "llm-wiki"}` (existence check via `list_wikis`), plus generated start page (compact overview linking the MOCs + article count) published with `start_page: true`.
- [x] T03 -- Publish executor: sequential `write_article` for created/changed, `delete_object` for locally-deleted slugs, re-publish restores archived slugs; per-article fail-soft (server secret-gate reject → skip + WARNING in the errors-log, run continues); state manifest updated per article only on server success.
- [x] T04 -- Lifecycle integration test mirroring the REFERENCE PRODUCER RUN semantics (`wiki-tools.test.ts:266` in context-mcp) against a fake in-process JSON-RPC server: publish → update (version bump) → retract → re-publish-restores; the fake server REPLICATES the server-side `slugifySkillName` re-slugification (asserting the S01 fixpoint property end-to-end); at least one test drives the real client + executor unmocked at the seam (mocks-mask-wiring rule).
- [ ] T05 -- First full live publish of the lxw vault against `dev.meinkontext.de`: mint the operator token per the live-import runbook (`docs/setup/MCP-CONNECT.md`, context-mcp), run `wiki publish`, verify article counts via `list_wikis`/dashboard, rerun proves zero writes. Record evidence in the task summary.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- 2026-08-25 (operator catch, post-T04): `MEINKONTEXT_TOKEN` was missing from the seeded `templates/.claude/.env.example` — added with runbook pointer + iCloud caution (`3e97c32`). Template-resync rule: env-var additions belong in the same commit as the code that reads them; T01 missed it.
- WATCH-ITEM (architect review 2026-08-25): upstream tests retract via `svc.archive()` directly, not via the `delete_object` TOOL, and `delete_object`'s description text is stale ("currently NO restore") vs contract §Lifecycle 5 (run wins). T05 + S03-T02 are the first real proof of the tool-surface retract/restore path — on any deviation, report upstream via operator tasking (REGEL #2), do not work around silently.
