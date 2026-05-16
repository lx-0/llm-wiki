---
milestone: M007
project: llm-wiki
size: M
created: 2026-05-16T15:01:00Z
status: done
total_slices: 3
completed_slices: 3
---

# M007 Roadmap

**Goal:** Ship a `compile_role` frontmatter axis with 3 values that lets compile.py treat any vault page as substrate (distill into knowledge/), source-and-final (index without distilling), or final-only (engine-skip).

**Exit criteria:**
1. `compile_role` enum recognized + lint-validated.
2. compile.py branches 3-way per role.
3. Dashboard + MOC + `wiki query` filter `final-only` from active surfaces.
4. ≥1 longform import from `imported/lx/` tagged `source-and-final` surfacing correctly.
5. `archives-flag.md` retired (subsumed).

## Slices

Slice detail lives in per-slice `M007-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 -- Schema foundation: compile_role enum + config knob + lint validation (4 tasks)
- [x] S02 -- compile.py 3-way dispatch: source-only / source-and-final / final-only (5 tasks)
- [x] S03 -- Active-surface filtering + lx longform validation + archives-flag retire (6 tasks)

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
