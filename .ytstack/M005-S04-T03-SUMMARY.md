---
milestone: M005
slice: S04
task: T03
project: llm-wiki
closed: 2026-05-15T20:00:00Z
verification: passed
---

# M005-S04-T03 -- Summary

## Commits so far (auto-tracked)

- `7551daa` — feat(compile): resolution detection and demotion (M005-S04-T02). **NOT T03 work** — that's T02's closing commit; T03 was active when T02 closed.

## Outcome

Three artifacts under `tests/fixtures/lifecycle/`:

- `jane-doe-before.md` — entity page in State BEFORE the followup meeting. Carries 2 open Action Items (Q3 deck with `📅 2026-04-22 ⏫`, Bob intro), 1 Open Thread (Hetzner), correct two-layer structure.
- `jamie-followup-after.md` — synthetic jamie substrate where Jane confirms `"I sent the Q3 deck this morning"` (resolution signal), Alex confirms `"haven't done the intro yet"` (non-resolution, should carry forward), and Hetzner stays unresolved. The fixture's `## Expected lifecycle outcome` block encodes the canary truth-set: demote deck, carry-forward intro + Hetzner, append re-mention Timeline entry.
- `README.md` — contract doc for the lifecycle-fixture pattern.

`tests/test_lifecycle_resolution.py` — three test cases:

1. BEFORE-fixture carries the canonical open-commitment shape (the Read-first target).
2. AFTER-substrate carries the resolution signal (past-tense first-person announcement) AND the carry-forward signal AND the Hetzner-still-open signal.
3. Rendered prompt for the AFTER substrate contains the resolution-detection rule, the carry-forward rule, the substrate body unchanged, and the anti-false-positive guard.

Suite: 238 passed (235 + 3 new).

## Deviations from plan

None.

## Follow-ups

- T04 ships the symmetric fixture pair for manual-`[x]` preservation.
- Optional: extend `docs/m005-s03-canary-procedure.md` with a "Canary 4 — Lifecycle" section that points at this fixture pair for the operator to dry-run. Backlog candidate if not done in S04.

## Verification

```
test -f tests/fixtures/lifecycle/jane-doe-before.md && \
test -f tests/fixtures/lifecycle/jamie-followup-after.md && \
test -f tests/fixtures/lifecycle/README.md && echo OK
# → OK

uv run --project . pytest -q tests/test_lifecycle_resolution.py
# → 3 passed in 0.01s

uv run --project . pytest -q tests/
# → 238 passed in 0.53s (+3 from prior 235)
```

Result: **passed**.
