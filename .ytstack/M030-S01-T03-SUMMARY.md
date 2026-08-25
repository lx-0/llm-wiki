---
milestone: M030
slice: S01
task: T03
project: llm-wiki
closed: 2026-08-25T09:10:00Z
verification: passed
---

# M030-S01-T03 -- Summary

## Commits

- `feat(publish): description sourcing from index rows (M030-S01-T03)` (committed with this summary)

## Outcome

`scripts/publish/describe.py` produces the contract-required description per article: `description_index` parses the full `knowledge/index.md` rows (pipe-sentinel split for `\|`, Article-cell wikilink resolved via `core.links.resolve_link` from `index.md` as source) into `{rel: summary}`; `describe` returns index summary → first non-heading body paragraph (frontmatter stripped via `core.frontmatter.parse`) → article stem. Wikilinks in the chosen text collapse to alias-or-target; whitespace collapsed; hard cap at 1024 (1023 + ellipsis). Always non-empty.

## Deviations from plan

None.

## Follow-ups

None.

## Verification

Command: `uv run pytest tests/test_publish_describe.py -q` (6 passed) + `uv run pytest -q` (1809 passed, 1 pre-existing skip) -- passed.
