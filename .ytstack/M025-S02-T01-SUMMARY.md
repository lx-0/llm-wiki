---
milestone: M025
slice: S02
task: T01
project: llm-wiki
closed: 2026-06-25
verification: passed
---

# M025-S02-T01 — Summary

## Outcome

`core/capture_index.resolve_articles(knowledge_dir=None) -> {capture_id: [article_relpath]}`
is the S02 forward link: it joins the S01 capture index (`capture_id → source_path`)
against the `compiled_from` frontmatter the compile prompts stamp on `knowledge/**`
articles, returning, per captured id, the article(s) it was compiled into. An empty
list means recorded-but-not-yet-compiled (a valid observable state — e.g. captures that
are source-only). `{}` when the index is empty. Matching is by the capture **filename**
(`capture-<id>.md`), so a differing path prefix in `compiled_from` (e.g. `./raw/...`)
still joins. Helper `_compiled_from()` parses the YAML frontmatter block and normalises
the `str | list` shape. Pure filesystem scan — no compile/agent dependency, so S02 does
NOT forward-depend on S03's compile changes (sequential-slice rule).

## Deviations from plan

- Plan named the helper "expose a helper (e.g. `resolve_articles()`)" — kept that exact
  name in `core/capture_index` (the plan's preferred home), no new module.
- Filename-basename join (not full-path equality) chosen for robustness to prefix
  variance; covered by a dedicated test (`./raw/...` prefix still resolves).

## Verification

`uv run --project .wiki pytest tests/test_capture_index.py` — 9 passed (3 new:
list+string `compiled_from` join, basename-match across two articles, empty-index→`{}`
and absent-knowledge-dir→no-crash). Focused regression (index + collector): 26 passed.

## Follow-ups

- **T02** consumes `resolve_articles()` to render the daily-digest "Captures" section
  (capture-id → interpretation = resolved article + index status). Digest is
  agent-generated (`wiki agent daily-digest`) → enrich `daily/<date>/captures.md` +
  extend the `daily-digest` prompt.
- **T03** correction recognition (capture body references a known id → `kind: correction`
  + `corrects: <id>`); supersede write-back is S03.
