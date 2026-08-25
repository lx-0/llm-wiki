---
milestone: M030
slice: S01
task: T04
project: llm-wiki
closed: 2026-08-25T09:30:00Z
verification: passed
---

# M030-S01-T04 -- Summary

## Commits

- `feat(publish): content-hash delta engine (M030-S01-T04)` (committed with this summary)

## Outcome

`scripts/publish/delta.py` builds the wire payloads (`ArticlePayload`: slug, rel, name, description, link-normalized content, sha256 hash over name+description+content) and diffs them against the manifest: create / update / retract(slug, rel) / unchanged. The `name` rule guarantees server-side re-slugification reproduces our slug (pretty stem when `server_slug(stem) == slug`, else the slug itself — fixpoint-asserted in tests for disambiguated slugs). `record_published`/`record_retracted` write per-article manifest entries through the locked StateStore — the S02 executor calls them only after server success. Idempotency proven: rerun over unchanged input plans zero writes; description-only change (index summary edit) correctly triggers an update since description is a write_article argument.

## Deviations from plan

None.

## Follow-ups

None.

## Verification

Command: `uv run pytest tests/test_publish_delta.py -q` (6 passed) + `uv run pytest -q` (1815 passed, 1 pre-existing skip) -- passed.
