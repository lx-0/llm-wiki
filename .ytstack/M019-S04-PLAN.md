---
milestone: M019
slice: S04
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: done
task_count: 6
completed_tasks: 6
---

# M019-S04 — Slice Plan

**Goal:** Meta-report (`_summary.md`) as the primary consumption surface. Cross-instrument radar (current state + previous-run overlay for change-vis, activating by run 2) + coverage-sparkline (wiki-health-meter) + per-instrument timeline plots + embedded-methodology rendering across every report. PNG pipeline (matplotlib) established. Closeout backlog stub for post-wedge personality-substrate-predigestion (R2 forward).

## Tasks

- [x] T01 — **Markdown renderer via plain Python (no j2 dep).** ✓ Done 2026-05-17. Renderer lives at `scripts/reports/_engine/lib/render_summary.py` and assembles the meta-report from a list of section-emitting helpers. j2 dep dropped — the markdown shape is simple enough that f-string composition is clearer, and adding Jinja2 just for this surface would be over-engineering. The original "5 j2 partials" plan collapsed into one `render_summary()` function with inline section-builders.

- [x] T02 — **`lib/charts.py` — SVG (not matplotlib).** ✓ Done 2026-05-17. Three pure-Python SVG renderers: `render_sparkline()` (line plot 200×40 with last-point marker), `render_radar()` (polar polygon with optional previous-run dashed overlay, 4-level concentric gridlines, axis labels around perimeter, current+previous legend at bottom), `render_timeline()` (per-instrument double-line plot score+coverage with date stamps along X axis). SVG over matplotlib decision recorded in commit: avoids +30 MB matplotlib + numpy transitive dep weight for three geometrically-simple plots; SVG embeds directly in Obsidian markdown via `![title](charts/foo.svg)` and renders cleanly. Placeholder SVG with "activates by run 2" message emitted when input series has <2 points. ~400 LOC total including the palette + Point helper.

- [x] T03 — **`lib/timeline.py` — cross-run aggregation.** ✓ Done 2026-05-17. `InstrumentSnapshot` (frozen dataclass with slug + version + timestamp + total_score + band + bandable + coverage_pct + answered + total_items), `RunSnapshot` (per-run aggregate), `Timeline` (cross-run + `series_for()` + `latest` + `previous` + `all_instrument_keys()`). `load_timeline()` walks `<study>/runs/<ts>/instruments/*.md` (skips `.<ts>.tmp` atomic-write dirs), `snapshot_from_dir()` picks up an in-progress run from the tmp dir before atomic commit — critical for rendering the meta-report **inside** the same atomic-rename envelope as the per-instrument reports. Wedge runner.py uses this exact pattern.

- [x] T04 — **`_summary.md` renderer + wired into runner.py.** ✓ Done 2026-05-17. `render_summary()` writes: frontmatter (study_id, n_runs, avg_coverage, bandable_count), Informant-Report banner, Cross-instrument table (slug | score | band | coverage | Δ-vs-previous with em-dash on run 1), Cross-instrument radar inline-referenced, Coverage sparkline (placeholder on run 1; activates by run 2), Per-instrument timelines (one SVG each, activates by run 2), Convergence/discrepancy flags from `_crosscheck_flags()` (concerning bands + low-coverage outliers), Per-instrument detail pointers. Wired into `scripts/study.py:cmd_run` so meta-report renders inside the RunDirectory tmp dir BEFORE atomic-rename — atomic commit envelopes the whole run including summary + charts. Render-failure is soft (warn + continue) so a meta-render bug never invalidates the per-instrument reports.

- [x] T05 — **Embedded-methodology verifier.** ✓ Done 2026-05-17. `lib/verify_report.py` checks every per-instrument report against the durability contract: 8 required frontmatter keys (instrument, version, run_timestamp, total_score, model_id, prompt_version, scope, coverage), 4 required body sections (Score, Items, Per-item detail, Embedded methodology), 5 required `<details>` blocks (Items / Cutoffs / Instrument meta / Prompt rendered / Scope-resolved substrate paths), and the Informant-Report banner. Runner.py calls it after each report write and surfaces failures as warnings (wedge philosophy — don't abort full run on one bad report). 8 unit tests cover good-report-passes + each-missing-field-flagged + no-frontmatter-edge-case + required-lists-locked-against-drift.

- [x] T06 — **Closeout: informant-banner + R2 backlog stub.** ✓ Done 2026-05-17. (a) Informant-report banner — present in both the per-instrument runner.py output (already S02-T04) AND the meta-report `render_summary()` (wider methodology-summary banner). Verified by `verify_report.py` + the meta-report-renders-with-2-runs test which asserts `"Informant Report" in content`. (b) `.ytstack/backlog/personality-substrate-predigestion.md` written — covers the three R2-mitigation paths (RAG, per-substrate summarisation, per-subscale call-batching), recommends a hybrid (c+b) approach, projects $76/year cost post-wedge including personality, lists a 6-slice implementation plan, gating-condition documented. (c) DECISIONS.md milestone-closeout entry deferred to S05-T06 — M019 isn't actually done until the analyst-agent layer ships.

## Done when

- 4 reusable lib modules (render, charts, timeline, crosscheck).
- 3 chart types render correctly to PNG.
- `_summary.md` produced for `longitudinal-baseline` study, both run-1 (no overlay) and run-2 (radar overlay + sparkline + deltas).
- Embedded-methodology lint passes; every report self-contained.
- Backlog stub for personality-substrate-predigestion written.
- DECISIONS.md milestone-closeout entry committed.
- All 8 M019 exit criteria from M019-CONTEXT.md confirmed.

## Notes
