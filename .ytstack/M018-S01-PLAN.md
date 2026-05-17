---
milestone: M018
slice: S01
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M018-S01 — Slice Plan

**Goal:** Curated fixture vault under `tests/fixtures/compile-regression-vault/` locks the byte-identical baseline that every subsequent slice diffs against — refactor regressions surface in CI before they reach lxw.

## Tasks

- [ ] T01 -- Pick 20 sources covering each `compile_role` value (source-only × N, source-and-final × 2, final-only × 1) + each substrate-type (email / youtube / screenshots / pictures / voice / jamie / gmeet / calendar / health / longform). Copy real lxw samples (with PII scrubbed) into `tests/fixtures/compile-regression-vault/raw/`. Document the picking rationale in the fixture README.
- [ ] T02 -- Pre-compile the fixture vault via current `wiki compile` (HEAD before any extraction); snapshot the resulting `knowledge/` tree byte-for-byte into `tests/fixtures/compile-regression-vault/knowledge.expected/`. Hash-pin the expected outputs (sha256 sidecars).
- [ ] T03 -- Write `tests/test_compile_regression.py` that runs the engine against the fixture vault into a tmp output dir + diffs against the snapshot. Fail with structured diff on any byte mismatch. Pytest mark `@pytest.mark.slow` (it's a full compile run).
- [ ] T04 -- Document fixture-refresh procedure in `tests/fixtures/compile-regression-vault/README.md` (when intentional output changes land — e.g. prompt edit — operator regenerates `knowledge.expected/` + new sha256s + commits as the new baseline).

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Regression test exists, runs, currently passes (baseline = current `compile.py`).

## Notes

The fixture vault is the foundation: every subsequent slice's verification step is "regression test still green." Without S01 landing first, S02-S04 have no safety net. PII scrubbing: redact email addresses, real names not in `personal.implicit_operator_author`, and any account IDs — pattern-match against the lxw substrate, NOT manually.
