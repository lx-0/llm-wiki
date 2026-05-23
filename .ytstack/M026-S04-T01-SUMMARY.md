---
milestone: M026
slice: S04
task: T01
project: llm-wiki
closed: 2026-05-23T15:45:00+0200
verification: passed
---

# M026-S04-T01 -- Summary

## Outcome

The compile pipeline returns a typed `CompileOutcome` end-to-end. `compile_file` and
its three handlers (`_run_index_only`, `_run_health_stub`, `_run_compile_route`) now
return `CompileOutcome(status, skip_reason, failure_kind/detail, ingest_hash, cost/
tokens, article)` instead of the magic-key dict. `main()`'s loop matches
`outcome.status` and is the **single state-save site**: it persists
`state["ingested"][rel]=hash` iff `outcome.ingest_hash` (compiled, or the
source-and-final / health-stub deterministic skips). The `_STATE_MUTATING_SKIPS`
registry + its reload-after-skip dance (the leaky split-persist this milestone
targeted) are deleted, as is the dead `compile.py:_build_owner_block` (live copy lives
in `compile_stages/compile.py`). `CompileOutcome` gained an `article` field so the
agent's final text still reaches `run_post_passes`.

## Deviations from plan

- `CompileOutcome` needed an `article` field (missed in S01) so `_run_compile_route`'s
  success outcome could forward the article to `run_post_passes` — caught by the test
  suite (TypeError), added to `types.py` + CONTEXT.md.

## Follow-ups

- **Real-SDK lxw E2E NOT run** (exit-criterion item): a production `wiki compile` costs
  Claude tokens + mutates the operator's live vault, so it's the operator's call, not an
  autonomous action. The refactor is verified by 126 green tests incl. characterization
  tests that pass identically on the legacy and refactored `compile_file`. Operator runs
  `wiki compile` on lxw to confirm in production.
- Dead-branch follow-up (from S02): model size-escalation / force-long-context are
  unreachable for real data (all dispatch entries pin haiku) — separate decision.

## Verification

Command: `pytest tests/ -k compile` — 126 passed. `compile_file` return annotation is
`CompileOutcome`; `_STATE_MUTATING_SKIPS` + `_build_owner_block` confirmed gone (hasattr
False). Full suite: only 4 pre-existing `test_dream_sampling` time-drift failures remain
(untouched by M026). Committed `e9a44e5`.
