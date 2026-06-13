---
milestone: M028
slice: S01
task: T04
project: llm-wiki
closed: 2026-06-13T17:08:00+0200
verification: passed
---

# M028-S01-T04 -- Summary

## Commits

- `02f4e57` -- feat(correct): parse proposal contract + engine rename executor (M028-S01-T04, issue #5)

## Outcome

The proposal contract is now consumed engine-side. `_parse_proposed_actions(text)`
extracts the agent's fenced JSON `## Proposed actions` block (via
`parse_json_lenient`), shape-guards it to `{superseded, edited, renamed, deleted}`
lists, drops malformed `renamed` entries, and never raises. New
`core.links.rename_article(old, new, knowledge_dir, vault)` moves a file and
rewrites every wikilink (across knowledge articles + `index.md`) that resolved to
the old path — the engine-side replacement for the Bash `git mv` removed in T01.
`_execute_renames` runs the proposed renames in `apply()` after the agent loop,
skipping entries whose source is missing or target already exists. Deletions are
parsed but not executed (S02 owns the `.trash` executor).

## Deviations from plan

None. 4 files as planned. `rename_article` resolves links BEFORE moving (resolution
needs the file present); the moved file's own outgoing links are left for the
compile-time relativize pass + `wiki links` audit (noted in the docstring).

## Follow-ups

- T05 (next): ground-truth filesystem-delta reporting + divergence warning vs the
  agent's `## Applied summary` — the engine-executed renames are now known exactly,
  so reporting can be authoritative.
- Live agent behaviour on the full prompt+contract still unverified pending a gated
  SDK run (T06 mocks the SDK).

## Verification

Command: `uv run pytest tests/test_correct_apply.py tests/test_links.py -q &&
uv run pytest -q` -- passed. 3 parser tests (extract / garbage-default /
shape-guard) + 2 `rename_article` tests (move+rewrite / leave-unrelated). Full
suite **1330 passed, 1 skipped**.
