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
2. `select_sources()`, `compile_source()`, `commit_article()` exist as independently unit-testable functions; each ≥3 tests; first two are pure (LLM mocked).
3. Post-passes lift out of the per-file loop into `run_post_passes(source, compile_result)` consuming `ProducerRegistry.all()`.
4. End-to-end smoke: operator runs `wiki compile` on lxw post-Phase-2 and observes no crash + producer output still lands as before.
5. The 5 open questions in CONTEXT.md are CLOSED before S05 starts.

## Slices

(Filenames preserved from parallel-session slicing; S01 + S06 cancelled below.)

- [~] S01 -- ~~Fixture vault for regression check~~ — CANCELLED 2026-05-17 (premise-broken; LLM output non-deterministic, byte-identical diff is flaky-by-design)
- [ ] S02 -- Extract `select_sources()` — pure I/O (mtime / hash-skip / role-axis filter / dry-run). No LLM.
- [ ] S03 -- Extract `compile_source()` — LLM call with SDK mocked in tests. Owns prompt assembly + owner-block + pre-flight gate + kind-unknown retry + SDK call + failure classification.
- [ ] S04 -- Extract `commit_article()` — pure I/O. Writes to `knowledge/<bucket>/`, frontmatter merge, atomic-replace.
- [ ] S05 -- Lift post-passes via `run_post_passes()` consuming ProducerRegistry. Requires the 5 open questions closed.
- [~] S06 -- ~~Regression + closeout via fixture-vault comparison~~ — CANCELLED 2026-05-17 (depended on S01's fixture-vault premise; integration signal = manual operator smoke on lxw)

Active slices: S02 → S03 → S04 → S05.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed.
- Update `completed_slices` count.
- On milestone completion, flip `status: planned` → `status: done`.
- If new slices are added during execution, bump `total_slices`.
