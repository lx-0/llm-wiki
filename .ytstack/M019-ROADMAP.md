---
milestone: M019
project: llm-wiki
size: L
created: 2026-05-17T11:04:00Z
status: done
total_slices: 5
completed_slices: 5
parallel-with: M018
---

# M019 Roadmap

**Goal:** Ship the operator-self-reports wedge (c): inference-contract end-to-end with 3-layer scope-lock verified, 5 clinical-screen instruments inferred from substrate with embedded methodology, studies manifest + scheduled runs, and a meta-report with graphical change-visualization (radar overlay + coverage-sparkline + per-instrument timeline plots).

**Exit criteria:** see `M019-CONTEXT.md` § Exit criteria (8 items, including R1/R2/R3 verification gates from eng-review).

## Slices

Detailed slice plans at `M019-S##-PLAN.md`. Task counts: 5 / 5 / 5 / 6 / 6 = 27 total (L milestone, exceeds skill's 11–20 rubric upper bound — accepted because 3 of those tasks are mandatory verification gates from eng-review and S05 is the agent-analyst layer added post-eng-review per operator decision 2026-05-17).

- [x] S01 — Engine skeleton + R1 scope-lock wiring + DECISIONS.md entries + PHQ-9 scoring backbone (5 tasks) ✓ shipped 2026-05-17
- [x] S02 — Inference contract batched (R3) + R2 token-budget audit + first PHQ-9 inference run + 4 more instruments (5 tasks) ✓ shipped 2026-05-17
- [x] S03 — Studies manifest + atomic per-run persistence + flock + schedule + CLI subcommands + baseline study seed (5 tasks) ✓ shipped 2026-05-17
- [x] S04 — Deterministic meta-report (`_summary.md`) + SVG charts (sparkline/radar/timeline) + embedded-methodology verifier + R2 backlog stub (6 tasks) ✓ shipped 2026-05-17
- [x] S05 — Two-pass analyst-agent layer: Pass-1 per-study (`_analysis.md`) + Pass-2 cross-study (`reports/analyses/<ts>.md`) + flush.py piggyback + live verification + milestone-closeout (6 tasks) ✓ shipped 2026-05-17

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality. R1/R2/R3 verification gates are MANDATORY within their respective slices — wedge does not exit S01 without R1 documented, does not exit S02 without R2 + R3 confirmed.

## Parallel-milestone note

M019 runs parallel to M018 (compile.py split). Non-overlapping code paths:
- M018 touches `scripts/compile.py`, `scripts/core/`, `scripts/suggestions/`, pure refactor + producer-seam.
- M019 touches `scripts/reports/` (new sub-package), `scripts/cli.py` (new subcommand), `prompts/reports/` (new prompts), `templates/reports/` (new templates).

Both touch `config.py` + `config.example.yaml` + `migrate_config_keys.py` for their respective config keys — coordination required at commit time but no semantic conflict. Both touch `STATE.md` — last-write-wins; whichever session commits last sees the merge.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
