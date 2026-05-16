---
milestone: M007
slice: S02
project: llm-wiki
created: 2026-05-16T15:14:50Z
status: planned
task_count: 5
completed_tasks: 5
---

# M007-S02 -- Slice Plan

**Goal:** `compile.py` branches by `compile_role`: `source-only` (distill, today's behavior unchanged), `source-and-final` (indexed-only, no separate concept article), `final-only` (skip entirely). Engine-side 3-way dispatch with prompt branching.

## Tasks

- [x] T01 -- `compile.py` per-file dispatch on `compile_role` at top of per-file loop. `final-only` short-circuits with WARNING log entry (so operator sees it was skipped, not silently dropped). `source-only` falls through to current distill path. `source-and-final` routes to new index-only branch (T02). Touch: `scripts/compile.py::compile_one_file` (or equivalent entry-point).
- [x] T02 -- `source-and-final` index-only branch implementation. Extracts wikilinks from the file body, builds backlinks into `knowledge/connections/` candidates, surfaces in `knowledge/index.md` by its own pathname, but does **NOT** invoke the SDK distill call and does **NOT** produce a separate `knowledge/concepts/<title>.md`. Wikilink extraction via existing parser (grep `frontmatter.py` or similar for shared util — if none, factor one out in this task).
- [x] T03 -- `prompts/compile_main.md` updated with type-conditional rule: when an indexed-only page is referenced as a related/connected document, the prompt instructs the LLM to cite by pathname (not as `compiled_from`). Lift estimate: small prose change in the prompt, no structural rewrite.
- [x] T04 -- `knowledge/index.md` regeneration includes `source-and-final` entries by their pathname (e.g. `raw/notes/longform/yesterday-strategy-2026.md`), distinct from compiled `knowledge/**/*.md` entries. Index format change documented in AGENTS.md (covered in S03-T05). Touch: `scripts/dashboard/*` or wherever index.md is regenerated.
- [x] T05 -- Unit + integration tests in `tests/test_compile_role_dispatch.py`: (a) `final-only` file → no SDK call + log entry, (b) `source-and-final` file → wikilinks extracted + backlinks built + appears in knowledge/index.md + no concept file created, (c) `source-only` file → unchanged behavior (regression check), (d) end-to-end with a 3-file fixture exercising all paths.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
