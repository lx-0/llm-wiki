---
milestone: M005
slice: S03
task: T02
project: llm-wiki
closed: 2026-05-15T18:55:00Z
verification: passed
---

# M005-S03-T02 -- Summary

## Outcome

`prompts/compile_main.md` now carries a new sub-section **"Resolving the Owner to an entity page"** inside the commitment-extraction block. Five deterministic rules:

1. **Slugification**: lowercase + non-alphanum → `-` + collapse runs. Three worked examples (`Jane Doe` → `jane-doe`, `José García` → `jose-garcia`, `Bob (CEO)` → `bob`).
2. **Lookup order**: index.md grep → aliases-frontmatter grep across people pages → stub-creation if no hit.
3. **Disambiguation**: shared-attendee tiebreak, then most-recent-`updated:` page; never silent-merge; emit `## Open Threads` collision warning when context matches both.
4. **Stub-minimum shape**: full two-layer template with `aliases: []`, executive-blockquote `> First seen in ...`, `## State` (often `- **Role:** unknown`), the triggering commitment in `## Action Items`, empty Open Threads / body / See also, one-line Timeline entry.
5. **No stub for one-off mentions**: only commitments-by-speaker trigger stubbing.

`tests/test_compile_two_layer_prompt.py:test_compile_prompt_carries_entity_resolution_rule` asserts the rule headline, slug example, alias mechanism, disambiguation clause, and stub-guard all reach the rendered prompt.

## Deviations from plan

None.

## Follow-ups

- T03 audits `scripts/compile.py` to confirm the SDK options enable Edit/Write on `knowledge/people/` + `knowledge/projects/` paths (probably already true — let's verify).
- T04 fixture test exercises both T01 (extraction) + T02 (resolution) on a synthetic jamie transcript.
- T05 real-substrate canary.

## Verification

```
grep -E "Resolving the Owner|jane-doe|stub" prompts/compile_main.md
# → headline + slug example + multiple stub mentions

uv run --project . pytest -q tests/test_compile_two_layer_prompt.py
# → 4 passed in 0.01s

uv run --project . pytest -q tests/
# → 230 passed in 0.50s (+1 from prior 229)
```

Result: **passed**.
