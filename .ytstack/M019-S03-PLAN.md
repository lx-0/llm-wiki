---
milestone: M019
slice: S03
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: done
task_count: 5
completed_tasks: 5
---

# M019-S03 — Slice Plan

**Goal:** Studies manifest + per-run persistence under flock + scheduling semantics + `wiki study` CLI subcommands. Promotes ad-hoc per-instrument runs from S02 into managed studies with timestamped runs/ directories. First baseline study (`longitudinal-baseline`) seeded.

## Tasks

- [x] T01 — **`scripts/reports/_engine/study.py` schema + loader.** ✓ Done 2026-05-17. `InstrumentRef`, `StudyManifest`, `StudyState`, `Study` dataclasses with frozen-where-applicable. Validation: slug-rule (a-z0-9-, 3..64, no leading/trailing hyphen), schedule enum (manual|weekly|monthly|quarterly), unique aliases-per-manifest, source enum (inferred|form|both). `is_due(now)` honours `SCHEDULE_COOLDOWN_DAYS` (manual=never, weekly=7d, monthly=30d, quarterly=90d). `fork_study(src, new_id, root)` clones manifest with fresh state + "(fork)" title suffix. Compatible with `yaml.safe_load`/`yaml.safe_dump` round-trip.

- [x] T02 — **`RunDirectory` atomic-write helper.** ✓ Done 2026-05-17. Context-manager pattern: write into `<runs>/.<ts>.tmp/` then atomic rename to `<runs>/<ts>/` on `__exit__` with no exception. Exception during `with` block leaves `.tmp` dir for forensics + does NOT rename → partial runs don't poison timeline. Stale tmp from prior crashed run cleaned on enter. Collision with existing final dir raises `FileExistsError`. `instruments_dir` / `charts_dir` / `write(rel_path, content)` helpers.

- [x] T03 — **Per-study flock via `acquire_study_lock(study_id)`.** ✓ Done 2026-05-17. Mirror of compile.py's `_acquire_exclusive_lock`: `fcntl.flock(LOCK_EX | LOCK_NB)` on `STATE_DIR/study-<id>.lock`. Returns handle or None. Cross-study runs unblocked (per-study lock, not global). Slug-validated. Concurrent-acquire test passes (subprocess-held lock blocks second acquirer).

- [x] T04 — **Schedule via flush.py piggyback.** ✓ Done 2026-05-17. New piggyback entry `study_run_due` (cooldown 6h, enabled=False by default) registered in `_LEGACY_PIGGYBACK_COMMANDS`. Invokes `study.py piggyback` which iterates due studies + runs each (own per-study flock prevents double-runs). Config-knob migration entry shipped (per `feedback_config_change_requires_migration` memory). Default OFF — operator flips after S05 dogfooding completes.

- [x] T05 — **CLI subcommands + baseline study seed.** ✓ Done 2026-05-17. `wiki study list / run / new / diff (stub) / piggyback` subcommands wired in `scripts/study.py` + dispatched by `wiki` bash. Baseline study template at `templates/reports/studies/longitudinal-baseline/manifest.yaml` (5 wedge instruments, schedule=weekly for the cranked-cadence wedge boot). `lib/seed.sh` extended with section 8b that seeds study templates into vault `reports/studies/<id>/manifest.yaml` via the existing `_seed_file` helper. Smoke-tested: `wiki study new` / `--fork-from` / `list` all work; fork creates fresh-state child manifest. **38 new tests** at `tests/reports/test_study.py` covering manifest schema (good + bad slug + bad schedule + duplicate alias + missing-required + round-trip), state persistence, is_due across all 4 schedule values, fork-semantics (clones + collision + bad-slug), `RunDirectory` (happy path + exception keeps tmp + collision + stale-tmp-cleanup), `acquire_study_lock` (basic + concurrent-blocking subprocess test + bad-slug-rejected), `list_studies` (empty + skips-non-manifest + returns-sorted + tolerates-malformed). All 144 tests/reports/ tests green.

## Done when

- Manifest schema validates 5+ good and bad cases.
- Atomic-write pattern verified (no partial-run poisoning).
- flock prevents concurrent runs of the same study, allows parallel different-study runs.
- flush.py piggyback dispatches due studies.
- 4 CLI subcommands working (with `diff` stubbed).
- `longitudinal-baseline` seed lands in `templates/reports/` and survives `wiki seed --force`.
- One live run on lxw produces complete `runs/<timestamp>/` with all 5 instruments.

## Notes
