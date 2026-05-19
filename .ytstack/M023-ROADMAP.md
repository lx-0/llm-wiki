---
milestone: M023
project: llm-wiki
size: M
created: 2026-05-19T11:42:36Z
status: done
total_slices: 1
completed_slices: 1
---

# M023 Roadmap

**Goal:** All Apple Health data merges into the existing per-day health substrate, extending the timeline beyond Oura's 90-day window with weight, steps, workouts, sleep, HR from a 214 MB `Export.xml` drop.

**Exit criteria:**
- Per-day health files in `raw/notes/health/` contain merged HealthKit fields (weight, steps, workouts, sleep/HR where HealthKit covers a day Oura does not).

## Slices

Sliced merged into a single ad-hoc arc — operator said "implementiere" and "we have a plan, go forward" after planning, so the milestone shipped without per-slice plan files (Phase-1 pattern; same as `AD-HOC-health-phase-1-PLAN.md`).

- [x] S01 — adapter + collector + migration + config example + 27 tests + live lxw E2E (2599 files written, 3.8s, idempotent second pass) — shipped 2026-05-19

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
