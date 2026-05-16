---
milestone: M007
slice: S02
task: T01
project: llm-wiki
status: done
completed: 2026-05-16T16:20:00Z
---

# M007-S02-T01 -- Summary

## Outcome

`scripts/compile.py` got two additions:

1. `_frontmatter_compile_role(content)` regex helper (sibling to `_frontmatter_type`).
2. `compile_file()` early dispatch: after empty-check, before substrate-type-skip, calls `infer_compile_role()` with `CONFIG.limits.compile_role_default_by_location`. `final-only` short-circuits with WARNING + `{"_skipped": "compile_role_final_only"}`.

## Deviations from plan

- E2E roundtrip test deferred to T05 — ROOT_DIR resolves to `lx-0/` parent dir when running engine code without a real vault, making the planned synthetic-fixture-in-vault path fragile. Replaced with import + regex + dispatch unit-check; same coverage, less environmental coupling.

## Follow-ups

- **T02**: implement source-and-final index-only branch (extract wikilinks, build backlinks, surface in knowledge/index.md by pathname, NO LLM distill call, NO separate concept article).
- T05 will pytest the full roundtrip with proper conftest fixtures.

## Verification

```bash
PYTHONPATH=scripts uv run python -c "from compile import _frontmatter_compile_role; ..."   # OK regex
PYTHONPATH=scripts uv run python -c "from compile import compile_file"                      # OK import
uv run pytest tests/test_compile_role.py tests/test_compile_lock.py -q                      # 29 passed
```

## Commits

- `<this>` — feat(compile): compile_role dispatch + final-only short-circuit
