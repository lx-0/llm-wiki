---
milestone: M028
slice: S04
task: T03
project: llm-wiki
closed: 2026-06-13T18:52:00+0200
verification: passed
---

# M028-S04-T03 -- Summary

## Commits
- `408b454` -- docs(correct): document M028 + release 0.2.0 (M028-S04-T03, issue #5)

## Outcome
Released **0.2.0**: CHANGELOG entry + `pyproject.toml` version + `uv.lock`.
PROCESS.md §13 rewritten to the shipped behaviour (agent-proposes-engine-disposes,
sandbox, deletion gate + tree guard, `.trash`, ground-truth reporting, supersession
+ updated status table + status enum). AGENTS.md §197 corrected — it claimed
`apply()` was "unchanged", now describes the sandbox (agent-facing instruction,
was actively wrong). config.md documents `correct_apply_max_turns` +
`correct_broad_term_threshold`. DECISIONS shipped note + KNOWLEDGE
"agent proposes, engine disposes" pattern.

## Deviations from plan
None (docs/release task, no TDD).

## Follow-ups
T04 closeout: suite green (1356) + golden repro green (S01-T06); diagrams assessed
NOT portrait-worthy (per-command semantics below the steady-state altitude →
documented in PROCESS.md per CLAUDE.md rule); issue #5 close is GATED on operator go.

## Verification
`uv run pytest -q` → **1356 passed, 1 skipped**. `0.2.0` in pyproject + uv.lock + CHANGELOG.
