---
milestone: M018
slice: S01
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: planned
task_count: 4
completed_tasks: 0
supersedes: fixture-vault-regression (dropped 2026-05-17 — see ROADMAP)
---

# M018-S01 — Slice Plan

**Goal:** Pure I/O function `select_sources(criteria) → list[Path]` lives in `scripts/compile_stages/select.py` and replaces the scattered selection logic in `compile.py:main()`. No LLM, no state writes, no SDK imports.

## Tasks

- [ ] T01 -- Identify all selection logic in `compile.py:main()` (mtime-skip, hash-skip via state.json, role-axis filter from M007, `--dry-run`, `--file <path>` explicit mode, `compile_after_hour` cutoff, lock acquisition). Map each branch to where it'll live in the new pure function.
- [ ] T02 -- Create `scripts/compile_stages/` package + `select.py` module. Define `SelectCriteria` dataclass (mtime_threshold, role_filter, explicit_files, dry_run, after_hour_cutoff). Move pure selection logic into `select_sources(criteria, state) → list[Path]`. State arg is read-only.
- [ ] T03 -- Add `tests/test_select_sources.py` with ≥3 cases: (a) mtime-skip honors state.json hashes, (b) role-axis filter excludes `final-only` per M007, (c) `--dry-run` returns same list without side effects. Plus edge: empty vault returns `[]`.
- [ ] T04 -- Wire `compile.py:main()` to call `select_sources()` instead of inlined logic. Verify with `wiki compile --dry-run` on lxw (or local dev vault): same source list as pre-extraction. Lock-acquisition stays in `main()` for now (orchestrator scope is S04's call).

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `select_sources()` is independently importable, ≥3 unit tests, `wiki compile --dry-run` source list unchanged.

## Notes

This is the easiest extraction — pure I/O, no SDK coupling. Sets the pattern (dataclass criteria + pure function + tests) for S02 and S03. Resist the urge to extract `compile_source()` in the same slice — keep the extraction surface narrow per slice so smoke regressions are easy to localize.

**Note on dropped S01 fixture-vault concept:** The original M018-S01 was a curated byte-identical fixture vault for regression testing. Dropped 2026-05-17 because LLM output is non-deterministic (byte-compare flaky-by-design) + single-operator project where lxw is already the test bench. Regression signal = per-slice unit tests + manual lxw smoke after Phase 2. ROADMAP `total_slices` 6 → 4.
