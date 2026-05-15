---
milestone: M005
slice: S03
task: T01
project: llm-wiki
closed: 2026-05-15T18:45:00Z
verification: passed
---

# M005-S03-T01 -- Summary

## Outcome

`prompts/compile_main.md` Instruction 3 now contains an inline subsection **"Extracting commitments from meeting substrates"** that fires when `${source_path}` matches `raw/transcripts/jamie/*.md` or `raw/transcripts/gmeet/*.md`. It defines:

- The commitment quartet — Task / Owner / Deadline / Context
- Signal phrases to extract (`"I'll send X by Friday"`, `"Jane will follow up..."`) vs. signals to skip (idle mentions, hypotheticals)
- Four routing rules: known-person → their `## Action Items`; first-person operator → project's `## Action Items`; blocked/waiting → Owner's `## Open Threads`; unknown person → stub the page + route normally
- Mandatory Timeline citation on every entity page touched
- Anti-hallucination quality bar: "better to miss a fuzzy commitment than fabricate one"

`tests/test_compile_two_layer_prompt.py:test_compile_prompt_carries_commitment_extraction_rule` asserts the rule's marker headline, all four quartet bullets, both substrate-path prefixes, and the anti-hallucination clause reach the rendered prompt unchanged.

## Deviations from plan

Minor structural: the new rule landed as a subsection inside Instruction 3 (immediately after the two-layer schema rules), not as a new numbered Instruction 4. Reason: the commitment-extraction rule is conceptually one instruction with the two-layer schema (extraction *fills* the two-layer State block); making it a sibling sub-section is cleaner than renumbering Instructions 4-10. The verification test still asserts presence by content, not by section number.

## Follow-ups

- T02 deepens entity-resolution (already partly specified in the routing rules above — Grep `knowledge/index.md`; stub-creation fallback). T02 may codify a deterministic helper for the stub-creation case, or leave it LLM-driven and just tighten the prompt.
- T03 routing-correctness audit on `scripts/compile.py` — verify the SDK options allow Edit on `knowledge/people/` and `knowledge/projects/` paths (probably already true).
- T04 fixture test exercises this rule on a synthetic jamie file.
- T05 real-substrate canary verifies the LLM actually obeys the rule.

## Verification

```
grep -E "Extracting commitments|Task.*Owner.*Deadline" prompts/compile_main.md
# → "**Extracting commitments from meeting substrates.**" + quartet line

uv run --project . pytest -q tests/test_compile_two_layer_prompt.py
# → 3 passed in 0.01s

uv run --project . pytest -q tests/
# → 229 passed in 0.57s (+1 from prior 228)
```

Result: **passed**.
