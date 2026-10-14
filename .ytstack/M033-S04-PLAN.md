---
milestone: M033
slice: S04
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 7
completed_tasks: 0
---

# M033-S04 -- Slice Plan

**Goal:** No function in `scripts/` is ≥ 150 lines (AST-measured by a committed test with a shrinking allowlist), the four god modules are split where it pays, and every split is a pure move proven by the suite and the oracle.

## Tasks

- [ ] T01 -- The measurement as a test: `tests/test_function_length.py` walks `scripts/` with `ast`, fails on any function ≥ 150 lines not in an explicit allowlist (initially the 15 measured 2026-10-14, each with its line count), and fails when an allowlisted function has shrunk below the limit without being removed from the list — so the list can only shrink; generated tables (`core/config_schema.py`) excluded by path with a reason.
- [ ] T02 -- `dream.py` (2,014 lines): `dream_entity` (347) split along its phases (select → render prompt → SDK call → write-back → report); the module split into `dream/` (entity, sweep, candidates, web-research) if the function split exposes the seams; argv routing unchanged on the oracle and `wiki dream …` smoke.
- [ ] T03 -- Compile path: `compile.main` (317) and `_run_compile_route` (154) in `compile.py`, `compile_source` (212) in `compile_stages/compile.py` — extracted into the stage functions their comments already name (selection, retry ladder, failure classification, summary); `tests/test_compile_*` green, E2E smoke on three files (KNOWLEDGE "E2E smoke irreplaceable").
- [ ] T04 -- `core/sdk_helpers.run_sdk_query` (320): options build / stream loop / failure classification / cost accounting as separate functions behind the same signature; `tests/test_sdk_*` green; a live single-call probe through the harness.
- [ ] T05 -- Collectors: `gmeet._run_one_account` (295) and `calendar_collector._run_one_account` (188) split into fetch / transform / write phases mirroring each other; fixtures from the existing collector tests, output filenames byte-identical.
- [ ] T06 -- Producers + reports + CLIs: `curiosity/producer.maybe_generate_curiosity_requests` (292) + `maybe_generate_folder_requests` (202), `facts/takes_producer.maybe_extract_takes` (161), `reports/_engine/lib/render_summary.render_summary` (239), `reports/_engine/runner._persist_report` (192) + `run_inference` (164), `query.main` (236), `study.cmd_run` (222) — each split along its existing sections; allowlist in T01 empty at the end of this task.
- [ ] T07 -- God modules where it pays: `core/health.py` (1,644 → checks grouped by subsystem under `core/health/`), `lint.py` (1,284 → checks vs reporting), `cli.py` (1,040 → catalogue vs dispatch); `collectors/gmeet.py`, `core/sdk_helpers.py`, `migrations/migrate_config_keys.py` reviewed and left with a one-line reason in `docs/engine-layout.md` if not split; each module ≤ 1,000 lines or the reason stands.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- Seven tasks is the ceiling. If T07 does not fit the context budget after T02–T06, it becomes M033b per the CONTEXT's split rule rather than a looser task.
- Every task: suite ≥ 2,025 green, oracle byte-identical, no behaviour change in the move commit (defects found go into their own commit with a test).
