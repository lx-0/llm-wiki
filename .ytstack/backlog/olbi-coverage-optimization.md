# OLBI coverage + cost optimization

OLBI (Oldenburg Burnout Inventory, 16 items, 2 subscales —
Disengagement + Exhaustion) is the most expensive instrument on the
live longitudinal-baseline manifest and has the lowest coverage.

## Observed (run-7, 2026-05-17)

- **Coverage:** 6/16 = 37.5%
- **Cost:** $0.28 per run (Disengagement batch $0.14 + Exhaustion batch $0.14)
- **Comparison:** WHO-5 80% / $0.13 · GAD-7 57% / $0.17 · PSS-10 70%
  (with 2 operator-answers) / $0.12

OLBI sits at *worst-of-both* on the rebalanced 6-instrument manifest.
PHQ-9 / GAD-7 also have moderate coverage (44% / 57%) but cheaper and
narrower scope. OLBI's 16 items doubled the SDK fan-out without
proportionally adding signal.

## Three mitigation paths

1. **Operator-input on the weakest batch.** Use `wiki study answer` on
   the items the agent currently scores null. Reuses the M019 mechanism
   already shipped + adds operator-effort exactly where the substrate
   can't reach. Cheapest path. Reduces cost (the operator-answered
   items get excluded from the SDK prompt entirely) AND raises coverage.

2. **Fork to Exhaustion-only subscale.** OLBI's Disengagement subscale
   leans on attitudinal-toward-work items that need direct self-report.
   Exhaustion items are more behaviourally observable (sleep quality,
   energy levels — already in substrate via Oura + voice). Forking the
   instrument to Exhaustion-only-v1.0.0 would drop ~50% of cost + items.
   Trade-off: half the published instrument, half the construct
   validity. Documentation-discipline says explicitly call it a
   "subscale wedge", not "OLBI".

3. **Per-instrument Sonnet override** (same mechanism as ISI). Adds
   `inference.model: claude-sonnet-4-6` to OLBI's `instrument.yaml`.
   Empirically untested for OLBI; the ISI Sonnet override is itself
   still provisional (see DECISIONS.md 2026-05-17 "M019 post-wedge
   tuning"). Cost goes UP, not down — Sonnet is more expensive per
   token than Haiku. Only justified if coverage uplift is dramatic AND
   the per-run-cost ceiling holds.

## Recommendation order

Wait for the 2026-05-24 week-1 review. With 7 days of runs, the
variance band on OLBI coverage will be visible. If 37.5% is the floor
across all runs → path 1 (operator-input) first; if 37.5% is the
outlier and median is higher → no action needed.

Path 2 is the "concept rejection" outcome — fork only if path 1 yields
no uplift after operator engagement. Path 3 is the "throw money at
it" path; defer until ISI Sonnet override is itself verified.

## Status

**BACKLOGGED** — 2026-05-17. Decision belongs in `m019-week-1-review.md`
(2026-05-24 hard deadline). Don't act before then.
