---
milestone: M005
slice: S04
task: T04
project: llm-wiki
closed: 2026-05-15T20:15:00Z
verification: passed
---

# M005-S04-T04 -- Summary

## Commits so far (auto-tracked)

- `dd2c8a6` — test(lifecycle): resolution-demotion fixture pair (M005-S04-T03). **NOT T04 work** — T03's closing commit.

## Outcome

Two fixtures + one test file:

- `tests/fixtures/lifecycle/bob-smith-before.md` — Bob Smith entity page with `- [x] Sign the contract` (operator-checked) + `- [ ] Schedule onboarding call 📅 2026-04-15` (parallel open item) + open thread "Waiting on legal review of MSA Annex B".
- `tests/fixtures/lifecycle/email-touch-after.md` — substrate where Bob emails about an unrelated dashboard-staleness issue. Truth-set in `## Expected lifecycle outcome` block: PRESERVE both Action Items as-is (no resolution evidence either way), ADD new Action Item for the operator's "follow up by EOW" commitment, ADD Timeline entry for the substrate touch, do NOT demote the `[x]`.
- `tests/test_lifecycle_preservation.py` — three tests on BEFORE shape, AFTER neutrality, rendered-prompt preservation-rule presence.

Suite: 241 passed (238 + 3 new).

## Deviations from plan

One mid-task fix: the AFTER substrate's Summary line read "no mention of the contract" — which technically mentions "contract" in the body — and the strict test `test_after_substrate_does_not_mention_contract` flagged it. Rephrased to "substrate is silent on any prior commitments between operator and Bob" — same intent, no false-trigger. Caught by the very test it was meant to support.

## Follow-ups

- Lifecycle behaviour is now fully spec'd (T01+T02) + fixture-tested (T03+T04). The only step that remains is real-substrate canary validation — handled by the operator using `docs/m005-s03-canary-procedure.md`. A "Canary 4 — Lifecycle" section could be appended to that runbook pointing at these two fixture pairs; backlog candidate if not done in M005.

## Verification

```
test -f tests/fixtures/lifecycle/bob-smith-before.md && \
test -f tests/fixtures/lifecycle/email-touch-after.md && echo OK
# → OK

uv run --project . pytest -q tests/test_lifecycle_preservation.py
# → 3 passed in 0.01s

uv run --project . pytest -q tests/
# → 241 passed in 0.43s (+3 from prior 238)
```

Result: **passed**. **S04 closes.**
