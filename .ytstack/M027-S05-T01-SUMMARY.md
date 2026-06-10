---
milestone: M027
slice: S05
task: T01
project: llm-wiki
closed: 2026-06-10T23:55:00+0200
verification: passed
---

# M027-S05-T01 -- Summary

## Commits

- `c6922f6` -- feat(M027-S05-T01): pin compile-consumption chain + human-readable as_of date
- `db21099` -- plan(M027-S05-T01): pin the compile-consumption chain + as_of date

## Outcome

The compile-consumption chain for folder answers is pinned and the
as-of provenance is human-readable. Code-reality finding (recorded as
spec correction vs the slice plan's dream-primary wording): the chain
ALREADY worked — `list_raw_files` walks all of `raw/`, and
`type: note` routes through the email-deep-scan default dispatch.
Shipped: (1) `_render_answer` adds `as_of: YYYY-MM-DD` (UTC) beside the
`as_of_mtime` float — compile agent + operator read a date, the
staleness machinery keeps the float; (2) selection pin — a persisted
answer artifact appears in `list_raw_files()`; (3) routing-parity pin —
`decide_route` on a real answer yields the SAME
`(substrate_prompt, model_id)` as an email deep-scan, so a future
dedicated `note` dispatch forces a conscious folder decision. Dream
stays the secondary consumer (no code — it samples knowledge/, which
compile feeds).

## Deviations from plan

None — RED was exactly the one expected failure (`as_of:`); both pins
were green on first run, confirming the chain analysis.

## Follow-ups

- T02 next: the Q3 decision point — optional `sensitivity:` frontmatter
  on derived facts. Plan must OPEN with the decide (want it at all?);
  CONTEXT marked it nice-to-have, not a gate.
- T03 after: lxw e2e (exit criterion #6) — folder answer → compile →
  `knowledge/` fact → `wiki query` returns it with provenance.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py
tests/test_folder_curiosity_integration.py -q` then `uv run pytest -q`
-- passed. Full suite **1263 passed, 1 skipped** (1262 → 1263).
