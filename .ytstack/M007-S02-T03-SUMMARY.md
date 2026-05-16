---
milestone: M007
slice: S02
task: T03
project: llm-wiki
status: done
completed: 2026-05-16T16:35:00Z
---

# M007-S02-T03 -- Summary

## Outcome

`prompts/compile_main.md` got a 5-bullet block under section 7 explaining how to handle `compile_role: source-and-final` pages: cite by full pathname, no parallel `knowledge/concepts/` article, no `compiled_from:` entry. Connections-via-LLM still allowed (analysis on top of operator's writing).

## Deviations from plan

None.

## Follow-ups

T04: index.md regen so `source-and-final` entries are first-class (vs T02's append-on-compile pattern).

## Verification

`grep` confirms block present and well-formed.

## Commits

- `<this>` — docs(prompts): source-and-final reference rule
