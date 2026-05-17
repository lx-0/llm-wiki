---
milestone: M018
project: llm-wiki
size: L
created: 2026-05-17T12:45:00Z
status: planned
total_slices: 2
completed_slices: 1
---

# M018 Roadmap

**Goal:** Extract the LLM-call body from `compile.py:compile_file()` into `compile_stages/compile.py:compile_source()` (S02 ✓ shipped) + lift the post-pass loop into `run_post_passes()` consuming the ProducerRegistry from Phase 1 (S04). `select_files()` stays in compile.py (28 LOC, already factored — YAGNI). Knowledge/-writes stay agent-side via SDK tool-use (S03 cancelled — re-architecture not extraction).

**Exit criteria (revised 2026-05-17):**
1. ~~`<40 LOC` per-file loop body~~ — relaxed. With S03 dropped, knowledge/-write logic stays in the agent; compile_file() shrinks via S02 + S04 but not to that floor.
2. `compile_source()` (S02 ✓) exists as an independently unit-testable function with SDK-mocked tests.
3. Post-passes lift out of the per-file loop into `run_post_passes(source, compile_result)` consuming `ProducerRegistry.all()` (S04).
4. End-to-end smoke: operator runs `wiki compile` on lxw post-S04 and observes no crash + producer output (suggestions/curiosity/takes) still lands as before.
5. The 5 open questions in CONTEXT.md are CLOSED before S04 starts (✓).

## Slices

(Filenames preserved from parallel-session slicing; S01 + S03 + S05 + S06 cancelled.)

- [~] S01 -- ~~Fixture vault for regression check~~ — CANCELLED 2026-05-17 (LLM non-determinism; byte-identical diff is flaky-by-design)
- [x] S02 -- Extract `compile_source()` — SHIPPED 2026-05-17 (commits `3cd57bf` types, `b4f6c7b` extraction, `44a5dad` rewire, `5fa2aae` failure_detail fix)
- [~] S03 -- ~~Extract `commit_article()`~~ — CANCELLED 2026-05-17 (premise-broken: knowledge/-writes are agent-side via SDK tool-use, not in Python; full rationale in M018-CONTEXT.md + S03-PLAN.md cancellation block; deferred concept in `.ytstack/backlog/commit-article-manifest.md`)
- [ ] S04 -- Lift post-passes via `run_post_passes()` consuming ProducerRegistry.
- [~] S05 -- ~~(was post-pass lift)~~ — CANCELLED 2026-05-17 (folded into S04)
- [~] S06 -- ~~Regression + closeout via fixture-vault comparison~~ — CANCELLED 2026-05-17 (depended on S01)

Active remaining: S04. Dropped during planning: `select_sources()` extraction (YAGNI for 28-LOC factored function). Dropped during execution: `commit_article()` extraction (re-architecture, not extraction).

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed.
- Update `completed_slices` count.
- On milestone completion, flip `status: planned` → `status: done`.
- If new slices are added during execution, bump `total_slices`.
