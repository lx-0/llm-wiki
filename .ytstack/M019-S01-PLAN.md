---
milestone: M019
slice: S01
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: in-progress
task_count: 5
completed_tasks: 3
---

# M019-S01 — Slice Plan

**Goal:** Engine skeleton + scope-lock probe (R1) + air-gap structurally enforced + first instrument PHQ-9 scoring backbone end-to-end (no inference yet, just deterministic scoring + cutoffs against hand-filled input).

## Tasks

- [x] T01 — **R1 scope-lock wiring + verification probe.** ✓ Done 2026-05-17. Architecture refinement during execution: agents (inference + analyst) never write files themselves — output flows via TextBlock/ResultMessage and the engine persists deterministically. Scope-lock composition: `allowed_tools=["Read","Glob","Grep"]` + `disallowed_tools=["Write","Edit","NotebookEdit"]` + `permission_mode="default"` + `make_path_scope_gate([])` (empty-roots deny-all-writes, defense-in-depth). Probe at `scripts/reports/_engine/verify_scope_lock.py` ran 3 sub-probes (CONTROL-READ + WRITE-ATTEMPT + EDIT-ATTEMPT), all PASS, total cost $0.08. **Surprising finding:** model unprompted-escalated to `Bash sed` when Edit was denied — caught by `allowed_tools` whitelist not the scope-gate. Outcome documented in `.ytstack/KNOWLEDGE.md` ("M019 R1 wiring verified", 2026-05-17). Probe kept as regression. S02 + S05 use this exact composition verbatim.

- [x] T02 — **DECISIONS.md entries.** ✓ Done 2026-05-17. Three append-only entries: (a) `reports/` lives at vault root sibling of `knowledge/`, gitignored at engine repo. (b) Air-gap structural-not-lint, single-source-constant referenced by every compile-walker. (c) Claude SDK only for inference + analyst, no Ollama fallback (reproducibility of psychometric data depends on consistent model).

- [x] T03 — **Scaffold + air-gap.** ✓ Done 2026-05-17. `scripts/reports/_engine/`: `instrument.py` (yaml schema + loader, validates 8 required meta keys, item-id uniqueness, scoring strategy whitelist, achievable-range vs cutoffs match), `lib/likert.py` (LikertScale parse/validate/reverse + score_answers with reverse-coding + subscale aggregation + coverage_pct), `lib/cutoffs.py` (Band + Cutoffs.from_list + validate enforces contiguous-non-overlapping bands sorted by min + band_for lookup with out-of-range guard). Air-gap: `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES` constant in `core/config.py` (single source of truth), `is_compile_excluded_path()` helper in `core/utils.py`, applied as filter in `list_raw_files()` (belt-and-braces, redundant today since walker only enters daily/+raw/), `reports/**` added to `prompts/compile_main_system.md` SCOPE block as MUST NOT Read/Write/Edit. Tests: 61 pass (test_likert 21, test_cutoffs 17, test_instrument_yaml 7, test_compile_substrate_scope 16). No regressions in broader test suite from my changes (16 pre-existing failures from parallel-session prompt-template churn, unrelated).

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
