---
milestone: M028
slice: S01
task: T02
project: llm-wiki
closed: 2026-06-13T16:35:00+0200
verification: passed
---

# M028-S01-T02 -- Summary

## Commits

- `b114408` -- feat(correct): write-protect knowledge/facts/ in apply() sandbox (M028-S01-T02, issue #5)

## Outcome

`make_path_scope_hook` gained an optional `denied_subpaths` param: a Write/Edit
is now refused if it resolves inside a denied subpath, even when that path also
falls under an allowed root — deny takes precedence over allow. `apply()`'s
sandbox passes `denied_subpaths=[FACTS_DIR]`, so the agent can write across
`knowledge/` (concepts, projects, people, …), `daily/`, `index.md`, and the
operations log, but a write to `knowledge/facts/<slug>.md` is denied at the hook.
The fact source-of-truth is now structurally write-protected, not just
prompt-forbidden — closing the open item from T01.

## Deviations from plan

None. Touched exactly the 3 planned files (`sdk_helpers.py`,
`correct_apply.py`, `tests/test_sdk_helpers.py`). The `denied_subpaths`
default of `None` keeps the three existing callers (compile, dream, folder
provider) byte-identical — backward compat verified by the unchanged hook tests
staying green.

## Follow-ups

None new. Next: S01-T03 (rewrite `prompts/correct_apply.md` to
supersede-by-default + the structured-proposal contract).

## Verification

Command: `uv run pytest tests/test_sdk_helpers.py tests/test_correct_apply.py -q`
-- passed. 2 new hook tests (precedence + backward-compat default). Full suite
**1322 passed, 1 skipped**.
