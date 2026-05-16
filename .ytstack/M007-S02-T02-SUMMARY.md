---
milestone: M007
slice: S02
task: T02
project: llm-wiki
status: done
completed: 2026-05-16T16:30:00Z
---

# M007-S02-T02 -- Summary

## Outcome

scripts/compile.py: added source-and-final branch in compile_file() after the T01 final-only short-circuit. Extracts wikilinks via core.utils.extract_wikilinks, builds an index entry via build_index_entry (using frontmatter `title:` or filename-derived fallback), appends to knowledge/index.md if not already present (idempotent), returns `{"_skipped": "compile_role_source_and_final_indexed"}` — no SDK call, no separate concept article.

New helper `_frontmatter_field(content, key)` for scalar field extraction (sibling to _frontmatter_type and _frontmatter_compile_role).

## Deviations from plan

- Connections-build deferred. The slice plan mentioned "builds backlinks into knowledge/connections/ candidates". For T02 v1, wikilinks are extracted+logged but no programmatic backlink generation happens. Obsidian Graph picks up the wikilinks natively. Programmatic backlink generation is a follow-up if real demand surfaces.
- E2E real-INDEX-FILE write test deferred to T05 (proper fixtures).

## Follow-ups

- **T03**: prompts/compile_main.md type-conditional rule — when an indexed-only page is referenced as related/connected, cite by pathname (not compiled_from).
- **T04**: knowledge/index.md regen to natively include source-and-final entries (vs T02's append-on-compile pattern).
- **T05**: pytest with INDEX_FILE roundtrip fixtures.

## Verification

```bash
PYTHONPATH=scripts uv run python -c "from compile import _frontmatter_field"  # OK
uv run pytest tests/test_compile_role.py tests/test_compile_lock.py -q        # 29 passed
```

## Commits

- `<this>` — feat(compile): source-and-final index-only branch — M007-S02-T02
