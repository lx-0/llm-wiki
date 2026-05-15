---
milestone: M005
slice: S04
task: T01
project: llm-wiki
closed: 2026-05-15T19:40:00Z
verification: passed
---

# M005-S04-T01 -- Summary

## Outcome

`prompts/compile_main.md` Instruction 3 now carries a final lifecycle subsection **"Lifecycle: carry-forward and manual-check preservation"** with six rules:

1. Read first, rewrite second
2. Carry forward unresolved Action Items unchanged
3. Preserve manual `- [x]` checks (operator-owned state)
4. Deduplicate by task-phrase similarity; Timeline-cite re-mentions
5. Open Threads carry forward
6. Stale-flag (90+ days no evidence) instead of delete

Plus an anti-loss guard: if rewrite would produce FEWER Action Items than existed before, re-Read first.

`tests/test_compile_two_layer_prompt.py:test_compile_prompt_carries_lifecycle_rules` asserts headline + all six rule markers reach the rendered prompt.

## Deviations from plan

None.

## Follow-ups

- T02 adds the resolution-demotion logic: when substrate contains explicit resolution evidence ("sent the deck"), the matching State item moves to Timeline with `[resolved]` marker.
- T03 + T04 fixture-test both lifecycle directions.

## Verification

```
grep -E "Lifecycle: carry-forward|Read first|Preserve manual" prompts/compile_main.md
# → all three markers present

uv run --project . pytest -q tests/test_compile_two_layer_prompt.py
# → 5 passed in 0.01s

uv run --project . pytest -q tests/
# → 234 passed in 0.53s (+1 from prior 233)
```

Result: **passed**.
