---
milestone: M027
slice: S05
task: T02
project: llm-wiki
closed: 2026-06-11T00:40:00+0200
verification: passed
---

# M027-S05-T02 -- Summary

## Commits

- `f948145` -- feat(M027-S05-T02): sensitivity full build — root tag -> answer -> compile carry
- `c9f8df0` -- docs(DECISIONS): Q3 closed — sensitivity full build
- `3a04d3f` -- plan(M027-S05-T02): sensitivity full build — Q3 closed by operator

## Outcome

**Q3 closed by operator decision: full build** (over drop/minimal),
recorded in DECISIONS 2026-06-10. Three stages, marking-only (the walk
approval remains the content gate):

1. `personal.watched_folders` entries take an optional free-vocabulary
   `sensitivity: <string>` — schema validates non-empty-string-when-
   present; no migration (operator-authored sub-field like
   include/exclude); documented in config.example.yaml.
2. The folder backend resolves the entry (`_resolve_entry`, also now
   feeding `_resolve`) and stamps `sensitivity:` into the answer
   artifact's frontmatter when the root carries it — omitted otherwise
   (negative-asserted).
3. `prompts/compile_main.md` rule 11: substrate-agnostic carry — the
   same `sensitivity:` lands on every `knowledge/` article created or
   updated from a tagged source; never invented for untagged sources,
   never stripped on update from one.

## Deviations from plan

- None functional. Noted: a parallel session shipped 0.1.8 (thunderbird
  adapter fix + cleanup migration) onto `main` mid-task — zero file
  overlap verified (`git diff --stat` between my commits), suite green
  at the merged HEAD.

## Follow-ups

- T03 (last S05 task): lxw e2e for exit criterion #6 — and it now ALSO
  verifies the sensitivity carry empirically (prompt-level rule, not
  unit-testable).
- lxw config: the operator can set `sensitivity:` on `private-documents`
  / `work-company` whenever wanted — optional, no migration involved.
- None further for DECISIONS/KNOWLEDGE (decision recorded).

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py
tests/test_folder_index_collector.py -q` then `uv run pytest -q` --
passed. Full suite **1271 passed, 1 skipped** (1263 → 1271; +5 this
task, +3 parallel session).
