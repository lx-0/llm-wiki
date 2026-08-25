---
milestone: M030
slice: S02
task: T02
project: llm-wiki
closed: 2026-08-25T11:05:00Z
verification: passed
---

# M030-S02-T02 -- Summary

## Commits

- `feat(publish): wiki bootstrap + generated start page (M030-S02-T02)` (committed with this summary)

## Outcome

`scripts/publish/bootstrap.py`: `ensure_wiki` creates the managed wiki exactly once (`list_wikis` existence check, `create_wiki` with `managed_by: "llm-wiki"` — shapes mirrored from wiki-tools.ts: `{"wikis": [...]}` / `{"wiki": {...}}`). `start_page_payload` generates the entry article (article count + `[[slug]]` links to every `MOCs/` article; reserved slug `start`, collision raises). Its hash lives under the manifest's `start_page` key, never in `articles` — test proves the delta engine plans no phantom retraction for it.

## Deviations from plan

None.

## Follow-ups

None.

## Verification

Command: `uv run pytest tests/test_publish_bootstrap.py -q` (5 passed) + `uv run pytest -q` (1830 passed, 1 pre-existing skip) -- passed.
