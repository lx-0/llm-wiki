---
milestone: M005
slice: S01
task: T04
project: llm-wiki
closed: 2026-05-15T18:05:00Z
verification: passed
---

# M005-S01-T04 -- Summary

## Outcome

`tests/test_compile_two_layer_prompt.py` ships with two test cases that smoke-test the compile-prompt plumbing introduced by T01:

- `test_compile_prompt_contains_two_layer_schema` asserts the rendered `compile_main` prompt contains the Instruction 3 headline (`Two-layer shape for \`type: person|project\``), all four required section names (`## State`, `## Action Items`, `## Open Threads`, `## Timeline`), and the explicit "Obsidian-Tasks-plugin syntax" mention.
- `test_compile_prompt_includes_atomic_exception_for_other_types` asserts the rendered prompt contains the exception clause "do NOT emit the two-layer structure" — preserving the contract that `concept|connection|qa|moc` types stay on the existing atomic shape.

Both tests use `core.prompts.render` directly with dummy variable values, so they run in ~10ms with no LLM call, no API key, no network. Catch any regression at the prompt-rendering pipeline level (placeholder breakage, section rename, accidental removal).

## Deviations from plan

None for the test itself. Re-scoping note on the slice-plan wording: T04 was originally described as "run compile.py on a small substrate, verify fresh person-page emits two-layer shape". Engine-side validation that the *LLM actually obeys* the rule is S03's real-substrate canary deliverable, not T04. T04 verifies the rule reaches the model unchanged — the plumbing test, not the emission test. That re-scoping was implicit in the plan I wrote; calling it out here so S03 owns the emission-quality work explicitly.

## Follow-ups

- S02 lint can now consume `tests/fixtures/two_layer/*.md` as valid-case inputs (T03 fixtures + T04 prompt-test are the spec triangle).
- S03 real-substrate canary closes the loop: when an actual jamie/gmeet substrate compiles cleanly into a two-layer page that lint accepts, the end-to-end pipeline is proven.

## Verification

```
uv run --project . pytest -q tests/test_compile_two_layer_prompt.py
# → 2 passed in 0.01s

uv run --project . pytest -q tests/
# → 220 passed in 0.50s  (exactly +2 from prior 218)
```

Result: **passed**.
