---
milestone: M027
slice: S03
task: T04
project: llm-wiki
closed: 2026-06-10T19:55:00+0200
verification: passed
---

# M027-S03-T04 -- Summary

## Commits

- `b421fed` -- test(M027-S03-T04): true-chain integration tests for the folder pass
- `b7442d6` -- plan(M027-S03-T04): true-chain integration tests for the folder pass

## Outcome

`tests/test_folder_curiosity_integration.py` runs the full M027 folder
pass with only the LLM mocked: a fixture tree is walked by the real S02
collector (`walk_root` → `write_index`), the producer loads that real
digest and renders the REAL `compile_curiosity_folder.md` via the real
`render()` (the captured prompt proves digest content + template marker
flowed in), the emitted `folder-deep-scan` request is dispatched through
the real `cli._dispatch` into the real backend skeleton (dry-run resolves
the fixture file; after deleting it, the stale-index MISSING branch is
surfaced while dry-run still succeeds). Anchor and confidence are
verified over the REAL digest, vacuity-hardened: those tests also assert
the producer actually ran (prompt captured), so a silent gate-skip can't
fake a pass.

## Deviations from plan

None — single test file, zero production-code changes (the plan's "if the
chain exposes a seam bug, fix it" clause was not needed: no wiring bugs).

## Follow-ups

- Slice complete → run `/ytstack:reassess-roadmap`. S04 carries waiting
  there: provider seam (Q9), concrete answer landing
  (`raw/notes/folder/answer-<slug>.md` with provenance frontmatter incl.
  as-of mtime), informed-consent walk card (skeleton dry-run already
  prints the line), TCC/out-of-sandbox reader (Q5) is S06-adjacent.
- lxw activation note from T03 stands: next `wiki update` turns the
  producer on for real compiles; Q7 precision-tuning loop starts there.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_folder_curiosity_integration.py -q`
then `uv run pytest -q` -- passed. Full suite **1246 passed, 0 failed**
(1242 → 1246).
