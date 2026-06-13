---
milestone: M028
slice: S01
task: T03
project: llm-wiki
closed: 2026-06-13T16:52:00+0200
verification: passed
---

# M028-S01-T03 -- Summary

## Commits

- `477756e` -- feat(correct): supersede-by-default prompt + JSON proposal contract (M028-S01-T03, issue #5)

## Outcome

`prompts/correct_apply.md` was rewritten. The negation branch now **supersedes**:
the agent adds `status: superseded` + `superseded_by: facts/<slug>` +
`outdated_since:` to the article frontmatter and a `> [Superseded …]` banner under
the H1, keeping the body — with the verbatim rule "outdated != false — annotate,
never delete history." The agent has Write/Edit only (no shell) and emits a single
fenced JSON `## Proposed actions` block (`superseded`/`edited`/`renamed`/`deleted`)
that is the engine's source of truth for what to execute (T04 rename, S02 delete)
and cross-check (T05 reporting). Deletion nomination is gated by
`${deletion_allowed}`, threaded from `correct_apply.py` as `"false"` in S01.

## Deviations from plan

None. 3 files as planned. Design decision (operator-confirmed): the proposal
block is a **fenced JSON block** (jsonrepair-parseable, project LLM-output
convention) rather than re-parsing the human-readable `## Applied summary` — the
free-text-trust problem that caused issue #5.

## Follow-ups

- T04 adds the parser (`jsonrepair`) + rename executor consuming this contract.
- The agent's actual behaviour on the new prompt is UNVERIFIED until a gated live
  SDK run — T06 mocks the SDK; the real eval is the operator's paid step. Same
  posture as other compile-prompt changes.

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. 3 render-smoke tests (supersede keys + "outdated != false" + JSON
contract + deletion-gate token). Full suite **1325 passed, 1 skipped**.
