---
milestone: M005
slice: S04
task: T02
project: llm-wiki
closed: 2026-05-15T19:50:00Z
verification: passed
---

# M005-S04-T02 -- Summary

## Outcome

`prompts/compile_main.md` Instruction 3 now carries **"Resolution detection and demotion"** subsection covering:

- Five resolution-signal categories with example phrases (sent/delivered/met/decision/past-tense announcement)
- Task-phrase similarity matching procedure (verb + object, paraphrase-tolerant)
- Three-step demotion mechanic (REMOVE from State, APPEND to Timeline with `[resolved]` marker, never duplicate)
- Conservative bias for ambiguous signals (don't demote; cite Timeline-only)
- Confirmed-resolved special case for `[x]` + substrate-evidence (marker `[resolved-manual+substrate]`)
- Anti-false-positive guard: no demotion on hypothetical / future-tense statements

`tests/test_compile_two_layer_prompt.py:test_compile_prompt_carries_resolution_rules` asserts the headline, sample signals, demotion mechanic, marker syntax, anti-FP guard, and confirmed-resolved marker all reach the rendered prompt.

## Deviations from plan

None.

## Follow-ups

- T03 fixture-tests the resolution-demotion path (existing State + new substrate with resolution evidence → demoted Timeline entry).
- T04 fixture-tests the manual-`[x]` preservation path (operator-checked items survive re-compile).

## Verification

```
grep -E "Resolution detection and demotion|Sent the deck|resolved.*Timeline" prompts/compile_main.md
# → markers present

uv run --project . pytest -q tests/test_compile_two_layer_prompt.py
# → 6 passed in 0.02s

uv run --project . pytest -q tests/
# → 235 passed in 0.70s (+1 from prior 234)
```

Result: **passed**.
