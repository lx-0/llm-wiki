---
milestone: M027
slice: S02
task: T02
project: llm-wiki
closed: 2026-06-10T15:35:00+0200
verification: passed
---

# M027-S02-T02 -- Summary

## Commits

- `770c68f` -- feat(M027-S02-T02): render+write folder-index digest to raw/index/<root-id>.md
- `1ce761d` -- plan(M027-S02-T02): digest render+write to raw/index/<root-id>.md

## Outcome

`scripts/collectors/folder_index.py` now renders and writes the digest:
`render_index(index, *, max_tree_entries)` is a pure function
`FolderIndex -> markdown` — frontmatter carries `type: folder-index` (the
hook T03's compile-skip keys on), `root_id`, JSON-quoted `root_path`,
`generated_at`, the five counts flattened, and `truncated: true|false`;
the body has `## Recent changes` (per line: backticked rel_path + ISO
date + human size) and a depth-indented `## Tree` (dirs with trailing
`/`, files with size), capped at `max_tree_entries` with an
`_… N more entries omitted (size cap)_` marker. Names land verbatim —
unmasked per DECISIONS 2026-06-07. `write_index()` mkdirs
`INDEX_DIR = raw/index/` and overwrites `<root-id>.md` (one digest per
root, root_id used as-is). Deterministic: same FolderIndex in, byte-same
markdown out. 5 new tests (12 total in the module file).

## Deviations from plan

- Module is no longer stdlib-only (T01-era docstring claim): it imports
  `core.paths.RAW_DIR` for `INDEX_DIR` — same pattern as email backend's
  `DEEP_SCAN_DIR`. Docstring scope note updated. Still no config import.
- None otherwise — plan held.

## Follow-ups

- **T03 must hash modulo frontmatter** (or reuse walk-level signals):
  `generated_at` varies per walk, so a naive content hash never matches.
  Noted in the plan + `render_index` docstring.
- **T03 carries the compile-skip wiring**: add `folder-index` to
  `CONFIG.limits.compile_skip_substrate_types` default + migration entry
  (same-commit hard rule); carry-constraint — index = compile-skip,
  `raw/notes/folder/` answers = compile SOURCES.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_folder_index_collector.py -q` then
`uv run pytest -q` -- passed. 12/12 module tests green; full suite
**1219 passed, 0 failed** (was 1214 — no regression).
