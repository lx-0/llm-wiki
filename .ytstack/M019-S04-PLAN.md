---
milestone: M019
slice: S04
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: planned
task_count: 6
completed_tasks: 0
---

# M019-S04 — Slice Plan

**Goal:** Meta-report (`_summary.md`) as the primary consumption surface. Cross-instrument radar (current state + previous-run overlay for change-vis, activating by run 2) + coverage-sparkline (wiki-health-meter) + per-instrument timeline plots + embedded-methodology rendering across every report. PNG pipeline (matplotlib) established. Closeout backlog stub for post-wedge personality-substrate-predigestion (R2 forward).

## Tasks

- [ ] T01 — **`lib/render.py` — j2 markdown rendering with standard partials.** Partials: `header.j2` (study + timestamp + run-N), `score_block.j2` (per-instrument score + band + coverage), `subscale_table.j2` (multi-subscale instruments, used by ASRS Part A/B), `convergence_flags.j2` (cross-instrument convergence/discrepancy from `lib/crosscheck.py`), `embedded_methodology.j2` (collapsible `<details>` block with items + scoring + cutoffs + model-ID + prompt-version + scope-spec + per-item evidence inline). Per-instrument-report rendered via these partials in S04-T05. Unit-tests cover each partial with synthetic data.

- [ ] T02 — **`lib/charts.py` — matplotlib helpers + PNG outputs.** Three chart types: (a) `sparkline(coverage_series, out_path)` — coverage% over runs as light-weight inline-renderable PNG; (b) `radar(latest_scores, previous_scores | None, out_path)` — polar plot with one axis per instrument, normalized scores 0..1, current as solid polygon, previous as dashed overlay activating on run 2+; (c) `timeline_double_plot(score_series, coverage_series, out_path)` — line plot dual y-axis for per-instrument timeline page. PNG output to `runs/<timestamp>/charts/`. Decide Q2 (in-process matplotlib vs. shell-out): in-process for simplicity, document import-cost in KNOWLEDGE.md. Unit-tests assert PNG files written + non-empty + valid header bytes.

- [ ] T03 — **`lib/timeline.py` — cross-run aggregation.** Read all `runs/<timestamp>/instruments/<slug>.md` under a study, parse frontmatter (`total_score`, `band`, `coverage_pct`, `run_timestamp`), build `Timeline{per_instrument: {slug: [(ts, score, coverage)]}, study_id, n_runs}`. Drives both the meta-report current-vs-previous comparison and the per-instrument timeline plots. Unit-tests: timeline with 0 / 1 / 5 historical runs, missing-frontmatter recovery.

- [ ] T04 — **`_summary.md` (meta-report) renderer.** Reads `lib/timeline.py` aggregate + latest run; emits markdown with: cross-instrument radar inline (`![radar](charts/radar.png)`), coverage-sparkline inline (`![coverage](charts/coverage_sparkline.png)`), per-instrument current-state table (slug | score | band | coverage% | delta-vs-previous), convergence/discrepancy flags. Run-1 omits the previous-run overlay + delta column (writes "N/A — first run"). Run-2+ activates change-vis. Live-test on lxw: run `longitudinal-baseline` twice (week-spacing), confirm radar overlay visible + deltas computed.

- [ ] T05 — **Embedded-methodology rendering verified for every per-instrument report.** Render-time check: each per-instrument `.md` MUST contain — items (verbatim from items.yaml), scoring rules (verbatim from scoring.py docstring or instrument.yaml `scoring:` block), cutoffs (verbatim from cutoffs.yaml), model-id, prompt-version (hash of `prompts/reports/infer_instrument.md` at run time), scope-spec (the resolved file-list), per-item evidence (file paths + line + quote). Collapsed `<details>` blocks for readability but always present. Lint check at end of `wiki study run`: aborts run if any per-instrument report missing any of these fields. Verification: delete the engine source dir, open one report markdown — methodology is fully reconstructable from the file alone.

- [ ] T06 — **Closeout: informant-report banner (Q3) + post-wedge backlog stub (R2 forward) + DECISIONS.md milestone-closeout entry.** (a) Informant-report banner at top of every per-instrument report AND `_summary.md` header: short paragraph stating "This is an Informant Report — scores derived by LLM observation of operator's substrate, not self-report. Methodology embedded below. Counter-strategy: parallel `source: form` study available." Concrete wording locked in DECISIONS.md. (b) Write `.ytstack/backlog/personality-substrate-predigestion.md` covering the three R2-mitigation options (RAG, summarization-pass, per-subscale-batching) required before personality instruments (IPIP-NEO, HEXACO, PID-5) can run. (c) DECISIONS.md milestone-closeout entry summarizing what M019 locked architecturally.

## Done when

- 4 reusable lib modules (render, charts, timeline, crosscheck).
- 3 chart types render correctly to PNG.
- `_summary.md` produced for `longitudinal-baseline` study, both run-1 (no overlay) and run-2 (radar overlay + sparkline + deltas).
- Embedded-methodology lint passes; every report self-contained.
- Backlog stub for personality-substrate-predigestion written.
- DECISIONS.md milestone-closeout entry committed.
- All 8 M019 exit criteria from M019-CONTEXT.md confirmed.

## Notes
