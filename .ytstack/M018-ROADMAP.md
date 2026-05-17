---
milestone: M018
project: llm-wiki
size: L
created: 2026-05-17T12:45:00Z
status: planned
total_slices: 4
completed_slices: 0
---

# M018 Roadmap

**Goal:** `compile.py` is split into three pure stages (`select_sources`, `compile_source`, `commit_article`) plus a `run_post_passes()` orchestrator consuming the ProducerRegistry that landed in Phase 1 — so the per-file loop becomes thin, end-to-end testable, and the post-pass scheduling policy lives in one place instead of scattered through the per-file body.

**Exit criteria:**
1. `compile.py`'s `main()` per-file loop body fits in <40 LOC and contains zero LLM calls, zero file writes, zero state-save logic.
2. `select_sources()`, `compile_source()`, `commit_article()` exist as independently unit-testable functions; each ≥3 tests; first two are pure.
3. Post-passes lift out of the per-file loop into `run_post_passes(source, compile_result)` consuming `ProducerRegistry.all()`.
4. Regression: `wiki compile` on the curated fixture vault produces byte-identical `knowledge/` output BEFORE vs. AFTER.
5. The 5 open questions in CONTEXT.md are CLOSED before S05 starts.

## Slices

Slice detail lives in per-slice `M018-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [ ] S01 -- (to be planned)
- [ ] S02 -- (to be planned)
- [ ] S03 -- (to be planned)
- [ ] S04 -- (to be planned)

Suggested framing (from `.ytstack/backlog/producer-seam.md` lines 136–141, may grow to 5–6 slices during `slice-milestone`):

1. **Fixture vault for regression check** — curated 20-source set covering each role-axis value + each substrate-type. Locks the byte-identical comparison baseline.
2. **Extract `select_sources()`** — pure I/O (mtime / hash-skip / role-axis filter / dry-run). No LLM.
3. **Extract `compile_source()`** — pure LLM call. Owns prompt assembly + owner-block + pre-flight gate + kind-unknown retry + SDK call + failure classification. No file ops, no state I/O.
4. **Extract `commit_article()`** — pure I/O. Writes to `knowledge/<bucket>/`, frontmatter, atomic-replace.
5. **Lift post-passes out of per-file loop** — `run_post_passes()` orchestrator consumes ProducerRegistry. Requires the 5 open questions closed first.
6. **Scheduling-policy decision + regression verification** — fixture vault comparison; flip back the feature flags if dev-disabled.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality. The fixture-vault slice MUST land before any extraction slice so we can detect regressions immediately.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed.
- Update `completed_slices` count.
- On milestone completion, flip `status: planned` → `status: done`.
- If new slices are added during execution, bump `total_slices`.
