---
milestone: M005
slice: S03
project: llm-wiki
created: 2026-05-15T17:00:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M005-S03 -- Slice Plan

**Goal:** `compile.py` extracts commitments from jamie + gmeet transcripts (Task / Owner / Deadline / Context quartet) and routes them to the right entity's `## Action Items` or `## Open Threads`, with substrate citation in Timeline.

## Tasks

- [ ] T01 -- Compile-prompt rule -- LLM identifies commitments (Task/Owner/Deadline/Context) when reading jamie/gmeet substrates
- [ ] T02 -- Entity resolution -- given "Jane will send the deck", match speaker → `knowledge/people/jane-doe.md` (existing-entity match + create-stub fallback)
- [ ] T03 -- Routing logic in `scripts/compile.py` so extracted commitments land in the right entity page's State block, with Timeline citation of the source substrate
- [ ] T04 -- Fixture test -- `tests/fixtures/jamie/<canary>.md` with known commitments, verify compile emits correct items on correct pages
- [ ] T05 -- Real-substrate canary -- spot-check on one jamie + one gmeet meeting, iterate prompt if extraction quality is weak

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Fixture-test runs deterministic + green; real-substrate canary produces extraction quality the operator judges "good enough to dogfood".

## Notes

(Add observations during slice execution. Iteration on the extraction prompt is expected -- log prompt changes here.)
