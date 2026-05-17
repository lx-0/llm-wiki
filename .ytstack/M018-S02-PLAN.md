---
milestone: M018
slice: S02
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M018-S02 — Slice Plan

**Goal:** Pure I/O function `select_sources(criteria) → list[Path]` lives in `scripts/compile_stages/select.py` and replaces the scattered selection logic in `compile.py:main()`. No LLM, no state writes, no SDK imports.

## Tasks

- [ ] T01 -- Identify all selection logic in `compile.py:main()` (mtime-skip, hash-skip via state.json, role-axis filter from M007, `--dry-run`, `--file <path>` explicit mode, `compile_after_hour` cutoff, lock acquisition). Map each branch to where it'll live in the new pure function.
- [ ] T02 -- Create `scripts/compile_stages/` package + `select.py` module. Define `SelectCriteria` dataclass (mtime_threshold, role_filter, explicit_files, dry_run, after_hour_cutoff). Move pure selection logic into `select_sources(criteria, state) → list[Path]`. State arg is read-only.
- [ ] T03 -- Add `tests/test_select_sources.py` with ≥3 cases: (a) mtime-skip honors state.json hashes, (b) role-axis filter excludes `final-only` per M007, (c) `--dry-run` returns same list without side effects. Plus edge: empty vault returns `[]`.
- [ ] T04 -- Wire `compile.py:main()` to call `select_sources()` instead of inlined logic. Run the S01 regression test — must stay green. Lock-acquisition stays in `main()` for now (orchestrator scope is S05's call).

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `select_sources()` is independently importable, ≥3 unit tests, regression vault byte-identical.

## Notes

This is the easiest extraction — pure I/O, no SDK coupling. Sets the pattern (dataclass criteria + pure function + tests) for S03 and S04. Resist the urge to extract `compile_source()` in the same slice — bundling regresses the regression-test signal.
