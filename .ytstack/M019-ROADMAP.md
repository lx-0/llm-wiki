---
milestone: M019
project: llm-wiki
size: L
created: 2026-05-17T11:04:00Z
status: planned
total_slices: 4
completed_slices: 0
parallel-with: M018
---

# M019 Roadmap

**Goal:** Ship the operator-self-reports wedge (c): inference-contract end-to-end with 3-layer scope-lock verified, 5 clinical-screen instruments inferred from substrate with embedded methodology, studies manifest + scheduled runs, and a meta-report with graphical change-visualization (radar overlay + coverage-sparkline + per-instrument timeline plots).

**Exit criteria:** see `M019-CONTEXT.md` § Exit criteria (8 items, including R1/R2/R3 verification gates from eng-review).

## Slices

Slice detail lives in per-slice `M019-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [ ] S01 — Engine skeleton + scope-lock probe + first instrument end-to-end (to be planned)
- [ ] S02 — Inference contract batched + token-budget audit + 4 more instruments (to be planned)
- [ ] S03 — Studies manifest + flock + schedule + per-run persistence (to be planned)
- [ ] S04 — Meta-report layer with radar + sparkline + timeline + embedded-methodology rendering (to be planned)

## Suggested slice scope (refined during slice-milestone)

- **S01** — `reports/_engine/` skeleton, instrument-yaml schema, `lib/likert.py` + `lib/cutoffs.py`, first instrument PHQ-9 inferred end-to-end. **R1 probe** (3-layer scope-lock verification) runs in this slice before `lib/inference.py` is written. Air-gap recorded in DECISIONS.md. Q1 (filesystem location) resolved.
- **S02** — `lib/inference.py` with batched-by-subscale interface (R3 design from day 1), `lib/provenance.py`, scope-resolver, JSON-schema validator. **R2 token-budget audit** runs in this slice. 4 additional wedge instruments added (GAD-7, ASRS-v1.1, WHO-5, MEQ-19).
- **S03** — Studies manifest schema, `runs/` directory layout, flock at `STATE_DIR/study-<id>.lock`, schedule semantics (Q4 resolved), `wiki study run` + `wiki study list` CLI subcommands.
- **S04** — Meta-report layer: cross-instrument radar (matplotlib polar) with previous-run-overlay activating by run 2, coverage-sparkline, per-instrument timeline double-plots, embedded-methodology rendering. PNG pipeline established (Q2 resolved). Informant-report banner (Q3 resolved).

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
