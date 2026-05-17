---
milestone: M019
slice: S01
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: in-progress
task_count: 5
completed_tasks: 1
---

# M019-S01 — Slice Plan

**Goal:** Engine skeleton + scope-lock probe (R1) + air-gap structurally enforced + first instrument PHQ-9 scoring backbone end-to-end (no inference yet, just deterministic scoring + cutoffs against hand-filled input).

## Tasks

- [x] T01 — **R1 scope-lock wiring + verification probe.** ✓ Done 2026-05-17. Architecture refinement during execution: agents (inference + analyst) never write files themselves — output flows via TextBlock/ResultMessage and the engine persists deterministically. Scope-lock composition: `allowed_tools=["Read","Glob","Grep"]` + `disallowed_tools=["Write","Edit","NotebookEdit"]` + `permission_mode="default"` + `make_path_scope_gate([])` (empty-roots deny-all-writes, defense-in-depth). Probe at `scripts/reports/_engine/verify_scope_lock.py` ran 3 sub-probes (CONTROL-READ + WRITE-ATTEMPT + EDIT-ATTEMPT), all PASS, total cost $0.08. **Surprising finding:** model unprompted-escalated to `Bash sed` when Edit was denied — caught by `allowed_tools` whitelist not the scope-gate. Outcome documented in `.ytstack/KNOWLEDGE.md` ("M019 R1 wiring verified", 2026-05-17). Probe kept as regression. S02 + S05 use this exact composition verbatim.

- [ ] T02 — **DECISIONS.md entries:** (a) `reports/` filesystem location decided as vault root sibling of `knowledge/` (operator-visible, version-controllable in operator's git, separate from engine state in `.wiki/`). (b) Air-gap from compile-loop structurally enforced via hard-coded `disallowed_paths=["reports/"]` in compile.py substrate-scope-spec, not lint-warn. (c) Inference = Claude SDK only, curiosity = Ollama only, no cross-fallback. Both entries append-only in `.ytstack/DECISIONS.md`.

- [ ] T03 — **Scaffold `scripts/reports/_engine/` sub-package:** `__init__.py`, `instrument.py` (instrument-yaml schema + loader + validator), `lib/likert.py` (scale-agnostic scoring 0-3 / 1-5 / 1-7 + reverse-coding), `lib/cutoffs.py` (config-driven banding). Three unit-test files in `tests/reports/` covering Likert scoring (forward + reverse), cutoff banding (boundary conditions), instrument-yaml validation (good case + 3 bad cases). Verification: `uv run pytest tests/reports/ -v` green. Also: enforce `disallowed_paths=["reports/"]` in `scripts/compile.py` substrate-scope-spec from T02.

- [ ] T04 — **PHQ-9 instrument end-to-end (scoring only, no inference yet):** `scripts/reports/_engine/instruments/phq-9/v1.0.0/instrument.yaml` + `items.yaml` (9 PD items + `substrate_inferable` curated per-item) + `cutoffs.yaml` (5 bands per DSM-IV). Helper `score_instrument(instrument_id, version, answers_dict) -> Score` returns `total + band + per_item + coverage`. Unit-test with hand-filled answer arrays covering each band. Verification: `uv run pytest tests/reports/test_phq9_scoring.py -v` green.

- [ ] T05 — **Migration entry + config keys:** extend `scripts/migrations/migrate_config_keys.py` with `features.operator_reports: bool = False`, `personal.reports.studies_dir: str = "reports"` (relative to vault root per T02 decision), `personal.reports.weekly_window_days: int = 14` (initial schedule cadence). Add to `scripts/core/config.py` dataclass + `config.example.yaml` in same commit (per `feedback_config_change_requires_migration` memory). Verification: `wiki update` on a fresh vault writes the new keys with correct defaults.

## Done when

All tasks marked `[x]`. Specifically:
- R1 outcome documented in KNOWLEDGE.md
- DECISIONS.md has 3 new entries
- `uv run pytest tests/reports/ -v` green
- `wiki update` on test vault writes new config keys
- `reports/` is structurally excluded from compile.py substrate-scope

## Notes

(Observations during execution land here. Promote architectural surprises to DECISIONS.md, gotchas to KNOWLEDGE.md.)
