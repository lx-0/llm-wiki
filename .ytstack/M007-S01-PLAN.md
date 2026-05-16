---
milestone: M007
slice: S01
project: llm-wiki
created: 2026-05-16T15:14:50Z
status: planned
task_count: 4
completed_tasks: 1
---

# M007-S01 -- Slice Plan

**Goal:** `compile_role` enum recognized in frontmatter + config knob + lint validation. Schema foundation that everything downstream composes on.

## Tasks

- [x] T01 -- Add `compile_role` enum to frontmatter schema + default-by-location inference helper (raw/ → source-only, knowledge/ → final-only-or-distilled). Add to `scripts/core/frontmatter.py` (or schema location); helper function `infer_compile_role(path: Path, frontmatter: dict) -> CompileRole` with explicit-override-wins semantics.
- [ ] T02 -- Add config knob `compile_role_default_by_location: bool = true` in `scripts/core/config.py` + `config.example.yaml` + `scripts/migrations/migrate_config_keys.py` (**same commit per project hard-rule**: any +/- on config.py or config.example.yaml requires extending migrate_config_keys.py).
- [ ] T03 -- Lint validates enum + warns on cross-location moves without explicit override. Add `check_compile_role` in `scripts/lint.py`: rejects unknown enum values (fail), warns when a file moved location-class without explicit `compile_role` in frontmatter (warn-only).
- [ ] T04 -- Unit tests in `tests/test_compile_role_schema.py` covering: (a) enum recognition + rejection of bad values, (b) default-by-location inference for all 3 roles, (c) explicit override beats inference, (d) lint warnings fire on cross-location moves, (e) config-knob toggle disables inference cleanly.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
