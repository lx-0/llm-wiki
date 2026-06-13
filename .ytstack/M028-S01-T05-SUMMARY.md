---
milestone: M028
slice: S01
task: T05
project: llm-wiki
closed: 2026-06-13T17:18:00+0200
verification: passed
---

# M028-S01-T05 -- Summary

## Commits

- `2e1c060` -- feat(correct): ground-truth filesystem-delta reporting (M028-S01-T05, issue #5)

## Outcome

`apply()` now reports the real filesystem delta after the run instead of trusting
the agent's prose. `_git_delta(vault)` runs `git status --porcelain` (scoped to
`knowledge/`) when the vault is a repo; otherwise `_delta_from_snapshot` diffs a
pre/post mtime+size snapshot. `_divergence(actions, delta)` returns warnings when
the real delta contradicts the agent's declared proposal — the load-bearing check
being "more files deleted than declared", the exact issue-#5 failure (declared 6,
deleted 17). `_report_filesystem_delta` logs the created/modified/renamed/deleted
counts + paths and each divergence as a WARNING.

## Deviations from plan

None. 2 files as planned. All classification logic is pure helpers
(`_parse_porcelain`, `_snapshot`, `_delta_from_snapshot`, `_divergence`)
unit-testable without a git repo. One GREEN-phase code fix: the deletion warning
wording was changed to contain "deleted" (was "deletion(s)") to match the spec.

Caveat noted: in S01 git porcelain can include pre-existing dirty files in the
tree; S02-T04's dirty-tree guard tightens this so the delta reflects only the
apply's changes.

## Follow-ups

- T06 (last in S01): golden repro test — the issue-#5 scenario over a fixture
  vault deletes 0 articles, the hook denies an out-of-scope write, and the
  divergence path is exercised with a stubbed lying summary.

## Verification

Command: `uv run pytest tests/test_correct_apply.py -q && uv run pytest -q`
-- passed. 4 reporting tests (porcelain classify / snapshot delta / divergence
fires / divergence silent). Full suite **1334 passed, 1 skipped**.
