---
milestone: M030
slice: S01
task: T01
project: llm-wiki
closed: 2026-08-25T08:20:00Z
verification: passed
---

# M030-S01-T01 -- Summary

## Commits

- `7625d8f` -- feat(publish): corpus walker + fixpoint slug mapper + manifest store (M030-S01-T01)

(Task ref sits in the trailing parens, not as `M030-S01-T01:` prefix — listed manually.)

## Outcome

`scripts/publish/corpus.py` now maps the knowledge/ corpus to contract-shaped slugs. `server_slug` is an exact Python port of context-mcp's `slugifySkillName` (NFKD, strip U+0300–U+036F, lowercase, non-alnum runs → `-`, hyphen-trim; no truncation) and is fixpoint-tested. `map_slugs` walks via `core.links.iter_articles` (root index.md excluded), assigns flat global slugs with sorted, order-independent processing: prior-manifest paths keep their slug (retraction-id stability), contested bases disambiguate every newcomer to `parent-stem`, empty slugs and >120-char names raise ValueError, surviving collisions raise `PublishCollisionError` naming both paths. Manifest persistence (`{"articles": {slug: {"path": rel}}}`) runs through a `StateStore` at `STATE_DIR/publish.json` (locked, atomic), preserving unknown per-article keys for T04's hash fields.

## Deviations from plan

Three, recorded in the plan's Deviations section: mapping values are rel-posix strings (not Path); `manifest_store` uses `StateStore` directly (not the `store_for` singleton — fresh instances observe disk truth); the 120-cap is a name-arg rejection, not a slug truncation (verified against the TS source — the architect review's "cap in slugify" summary was imprecise).

## Follow-ups

None new — S02's fake server must replicate `slugifySkillName` (already in S02-T04's task text).

## Verification

Command: `uv run pytest tests/test_publish_corpus.py -q` (19 passed) + `uv run pytest -q` (1792 passed, 1 pre-existing skip) -- passed.
