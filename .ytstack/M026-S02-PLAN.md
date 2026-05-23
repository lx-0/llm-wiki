---
milestone: M026
slice: S02
project: llm-wiki
created: 2026-05-23T14:25:00+0200
status: planned
task_count: 2
completed_tasks: 2
---

# M026-S02 -- Slice Plan

**Goal:** Extract the pure routing decision out of `compile_file` into
`compile_stages/route.py:decide_route(source, content) → Route`. The
substrate→model/max_turns precedence ladder becomes a table-testable pure
function. No behavior change.

## Tasks

- [x] T01 -- Build `decide_route` + relocate its helpers. Move `SUBSTRATE_PROMPTS`,
  `_DEFAULT_DISPATCH`, `_SUBSTRATE_PATH_FALLBACKS`, `_substrate_key`,
  `_frontmatter_type/_compile_role/_field`, `_parse_frontmatter`,
  `_health_rollup_body_is_stub` from `compile.py` into `route.py`; `compile.py`
  re-imports them (existing uses + `test_compile_role_dispatch`'s `from compile import …`
  keep working). Implement `decide_route` (pure: no logging, no I/O, no state).
  **Nothing calls it yet** → provably zero behavior change. Table-tests.
- [x] T02 -- Wire `compile_file` to `decide_route` + `match`, executing each branch
  inline exactly as today. Logging reconstructed in `compile_file` from the `Route` +
  content. Behavior identical. Full suite green + `wiki compile --dry-run` smoke.

## Done when

Both `[x]`, verified. `decide_route` table-tested; full compile suite green; dry-run
smoke unchanged.

## Notes

- `decide_route` builds `CompileMetadata` with `project_slug=None`/`project_page_rel=None`
  — memory pre-pass is I/O, stays execution-side (T02 / S03).
- `_category_badge` stays in `compile.py`.
- Two isolated commits (build-unused, then wire) keep the behavior-risk step bisectable.
