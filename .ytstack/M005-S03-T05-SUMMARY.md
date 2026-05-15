---
milestone: M005
slice: S03
task: T05
project: llm-wiki
closed: 2026-05-15T19:30:00Z
verification: passed
---

# M005-S03-T05 -- Summary

## Commits so far (auto-tracked by post-tool-use-bash hook)

- `2d38cd3` — test(jamie): synthetic fixture + plumbing tests (M005-S03-T04). **NOT T05 work** — that's the T04-closing commit; T05 was active when T04 closed.

## Outcome

`docs/m005-s03-canary-procedure.md` shipped. A canary runbook for the operator to validate LLM emission against real substrates. Three canary substrates:

1. **Synthetic fixture** (cheapest) — `tests/fixtures/jamie/2026-04-15--canary-q1-review--abc.md` copied into a live vault and compiled. Truth-set explicit in the fixture's `## Expected extraction` block. Exact grep commands and pass/fail/caveat decisions per verifiable claim.
2. **Live jamie meeting** — operator picks a recent jamie file with ≥2 attendees and an explicit commitment; runs `wiki compile --only`. Same grep-based pass/fail logic.
3. **Live gmeet meeting** — same drill, accounting for gmeet's `## Summary` + `## Transcript` paired sections and different speaker-label conventions.

The doc encodes a **precision-over-recall** philosophy: false positives (hallucinated commitments) are worse than false negatives (missed real ones). Pass/fail criteria are falsifiable, not vibes.

If canaries fail persistently, the doc names the iteration knobs and the rollback path (`M005-S01-T01` head).

## Deviations from plan

The slice-plan implied T05 would actually run the compile in this session. Reality: the engine repo isn't a vault — `RAW_DIR` / `DAILY_DIR` don't exist here, so `compile.py` can't run. Engine-side T05 deliverable is intrinsically a **runbook for the operator**, not an executed canary. Documented this honestly in the procedure doc.

If the operator wants a fully-baked emission validation in CI, that's a future work item: stand up a minimal fake-vault fixture environment with mocked Claude SDK responses, run compile end-to-end, assert emitted file shapes. Out of scope for M005.

## Follow-ups

- **Operator action**: run canary 1 (synthetic fixture) — cheapest, most controlled. Use as gate to canary 2/3.
- DECISIONS.md gets a 1-line entry after each canary records PASS / PASS-with-caveats / FAIL.
- If canary fails: name the failure in DECISIONS.md, iterate prompt, re-canary. Persistent failure = roll back to `M005-S01-T01` head and rescope.

## Verification

```
test -f docs/m005-s03-canary-procedure.md && echo OK
# → OK

grep -cE '^## Canary [123]' docs/m005-s03-canary-procedure.md
# → 3

grep -cE 'PASS|FAIL' docs/m005-s03-canary-procedure.md
# → 12

uv run --project . pytest -q tests/
# → 233 passed in 0.57s (unchanged — doc only, no code)
```

Result: **passed**. S03 closes with a clear human-in-the-loop next step.
