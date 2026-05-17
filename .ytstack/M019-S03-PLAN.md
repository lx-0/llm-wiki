---
milestone: M019
slice: S03
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M019-S03 — Slice Plan

**Goal:** Studies manifest + per-run persistence under flock + scheduling semantics + `wiki study` CLI subcommands. Promotes ad-hoc per-instrument runs from S02 into managed studies with timestamped runs/ directories. First baseline study (`longitudinal-baseline`) seeded.

## Tasks

- [ ] T01 — **`scripts/reports/_engine/study.py` — manifest schema + loader.** Pydantic-or-dataclass model for `manifest.yaml` (study_id slug rules, title, created, schedule enum, instruments list with version + source + alias). Validator rejects unknown instrument-slugs, duplicate aliases, invalid schedule values. Fork-semantics: `Study.fork_from(other_study_id, new_id)` clones manifest with new id + timestamp. Unit-tests: manifest load (good + 3 bad), fork (deep-copy verification), schedule-due check (`is_due(now: datetime) -> bool` based on last run + interval).

- [ ] T02 — **Per-run persistence layout + atomic writes.** `runs/<UTC-timestamp-iso>/` directory per study; subdirectories: `instruments/<slug>.md` (per-instrument detail report), `charts/` (PNG outputs reserved for S04), `_summary.md` (meta-report stub for S04). Write pattern: tmp-dir-then-atomic-rename so partial-run-on-crash doesn't poison the timeline. Helper `RunDirectory.create(study_id, timestamp) -> Path` + `RunDirectory.commit(tmp_path, final_path)`. Unit-tests cover atomic-rename success + partial-failure cleanup.

- [ ] T03 — **flock at study-level (mirror compile-spawn-lock pattern).** `wiki study run <id>` acquires `flock` on `STATE_DIR/study-<id>.lock` before doing work. Lock timeout 600s default. If lock held → exit 0 with "another run in progress for study <id>, skipping" (consistent with `flush.py` dashboard-refresh-lock from memory `project_compile_lock_shipped`). Cross-study runs do NOT block each other (per-study lock, not global). Unit-test: two parallel `wiki study run` invocations on same study, second returns skip; on different studies both proceed.

- [ ] T04 — **Schedule semantics via flush.py piggyback (Q4 resolved).** Schedule values: `weekly | quarterly | manual`. Studies with non-manual schedule + `(now - last_run) >= interval` get auto-triggered by `flush.py` piggyback (existing pattern). Per-study `last_run_at` persisted in `studies/<id>/state.yaml`. Initial cadence for `longitudinal-baseline` is `weekly` (per Q4 wedge agreement: cranked first 2 months, settles afterwards via operator manifest-edit). Unit-test: piggyback dispatch covers due-study, skips not-due-study.

- [ ] T05 — **CLI subcommands + baseline study seed.** Add `wiki study list`, `wiki study run <id> [--instrument <slug>]`, `wiki study new <id> [--fork-from <other>]`, `wiki study diff <run_a> <run_b>` (stub for S04 — just exits 0 with "available after S04 meta-report lands"). Seed `templates/reports/studies/longitudinal-baseline/manifest.yaml` with the 5 wedge instruments (all `source: inferred`, version pinned, `schedule: weekly`). Template ships via `wiki seed --force` per existing convention. Live-test: `wiki study run longitudinal-baseline` on lxw produces a full timestamped run-directory with 5 per-instrument reports.

## Done when

- Manifest schema validates 5+ good and bad cases.
- Atomic-write pattern verified (no partial-run poisoning).
- flock prevents concurrent runs of the same study, allows parallel different-study runs.
- flush.py piggyback dispatches due studies.
- 4 CLI subcommands working (with `diff` stubbed).
- `longitudinal-baseline` seed lands in `templates/reports/` and survives `wiki seed --force`.
- One live run on lxw produces complete `runs/<timestamp>/` with all 5 instruments.

## Notes
