---
milestone: M030
slice: S01
task: T02
project: llm-wiki
closed: 2026-08-25T08:45:00Z
verification: passed
---

# M030-S01-T02 -- Summary

## Commits

- see `feat(publish): wikilink normalization for served articles (M030-S01-T02)` (committed together with this summary)

## Outcome

`scripts/publish/render.py:normalize_links` rewrites an article's body for serving: links resolving to a published knowledge article (via `core.links.resolve_link` + the inverted T01 slug map) get their target replaced by the flat slug with embed-bang, `#heading`, `|alias` and table-escaped `\|` preserved; every other link (unresolvable, outside knowledge/, root index.md, media embeds) collapses to plain text (alias wins, else clean target). Frontmatter and code fences are untouched via `core.links._strip_frontmatter_and_fences` (documented in-repo private reuse — the wikilink grammar stays single-source). Link-free text round-trips byte-identical.

## Deviations from plan

None.

## Follow-ups

None.

## Verification

Command: `uv run pytest tests/test_publish_render.py -q` (11 passed) + `uv run pytest -q` (1803 passed, 1 pre-existing skip) -- passed.
