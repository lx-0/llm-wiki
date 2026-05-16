---
milestone: M007
slice: S02
task: T04
project: llm-wiki
status: done
completed: 2026-05-16T17:05:00Z
---

# M007-S02-T04 -- Summary

## Outcome

source-and-final branch in compile_file now updates state["ingested"][rel_path] = file_hash(source) + save_state after the index append. Lint's check_orphan_sources will no longer flag source-and-final files as "orphan_source". Re-runs of compile become true no-ops via the existing hash-skip in select_files.

## Deviations from plan

None.

## Follow-ups

T05: full pytest fixtures for end-to-end source-and-final roundtrip (write fixture, run compile_file, assert state + index + no SDK call). Now possible to assert state correctness too.

## Verification

```bash
PYTHONPATH=scripts uv run python -c "from compile import compile_file"  # OK
uv run pytest tests/test_compile_role.py tests/test_compile_lock.py -q  # 29 passed
```

## Commits

- `<this>` — feat(compile): source-and-final marks ingested + saves state
