---
milestone: M007
slice: S03
task: T03
project: llm-wiki
status: done
completed: 2026-05-16T17:45:00Z
---

# M007-S03-T03 -- Summary

## Outcome

scripts/query.py: --include-final-only argparse flag + prompt-context filter injected via facts_md. Default skips final-only; flag re-includes.

## Verification

`--help` shows the flag; 48 regression tests green.

## Commits

- `<this>` — feat(query): --include-final-only flag
