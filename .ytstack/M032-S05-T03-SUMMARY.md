---
milestone: M032
slice: S05
task: T03
project: llm-wiki
closed: 2026-10-14T16:32:00+02:00
verification: passed
---

# M032-S05-T03 -- Summary

## Commits

Committed together with this summary under the `M032-S05-T03:` ref — `git log --grep '^M032-S05-T03'`.

## Outcome

The Overview is complete: a 920 × 780 window with the hero figure, four stat tiles and five
cards. **Notes by type** — `ui/HBars.svelte`, one-hue horizontal bars (12 px, rounded data-end,
square at the baseline) with the `TypeBadge` as each row's identity and the count at the tip;
largest first, ties in the type wheel's order, tooltip "person · 8 notes · 19 %". **Capture,
last 24 h** — `ui/HeatStrip.svelte` over T01's `listeners.timeline`: 2 × 24 cells, the `--line`
track for nothing and four lightness steps of the accent (`--heat-1…4`, `oklch(from
var(--accent) L c h)`, more = darker on light, more = lighter on dark), hour ticks 00 / 06 / 12 /
18 + now, a scale legend, a tooltip per cell ("mic · 14:00–15:00 · 118 chunks"). **Health** —
the ring + word and the doctor rows with the engine's verbs, running / done / failed state,
fix hints, the Update app row. **Next up** — the merged action list (eight rows max) with verb
buttons and result pills, "Nothing to do — your wiki is current" when empty. A **Charts |
Table** control in the header swaps every chart for its `ui/DataTable.svelte` twin (numbers
right-aligned, tabular). Derivations are pure and tested: `typeBars`, `heatLevel` (quartiles of
a full 30 s-cadence hour), `hourTicks` (a clock tick within two bins of "now" yields),
`hourName`. The harness captures ten Overview states (default / empty / no-access / table /
run-done, light + dark) under the strict gate.

## Deviations from plan

- The ordinal ramp needed wider nominal steps: at ΔL 0.07 the rendered (gamut-mapped) light
  steps measured 0.056 — under the validator's 0.06 floor. Nominal 0.76 / 0.67 / 0.58 / 0.50
  (dark 0.48 / 0.57 / 0.66 / 0.76) renders at ≥ 0.06; both modes pass all four ordinal checks
  (light end 2.39 : 1 on `#ffffff`, 2.56 : 1 on `#1a1d21`). Measured, not assumed — the probe
  reads the colours back from a painted canvas pixel because `fillStyle` no longer serialises
  wide-gamut colours to hex.
- The table twin lost its visually-hidden `<caption>`: the layout gate flags an sr-only
  element as clipped text. The table carries `aria-label` instead; the figure's caption names
  it visibly.
- Fixture cadence varied (26 / 54 / 80 / 112+ chunks in the day) so every heat level renders
  and the probe can see all four classes.
- Column chart height 130, type rows 20 px, window 920 × 780: the grid still scrolls for the
  last Next up rows at the default size; the plan accepted that.

## Follow-ups

- T04 deletes Cockpit + Atlas, their CSS and IPC; the panel's Overview nav already opens this
  window, so the header's Cockpit/Atlas channels go with no renderer change.
- A `hover` harness state for the tooltip is still not captured (see T02 follow-ups).

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots …` + the ordinal
probe — passed (vitest 112 passed / 2 skipped incl. 5 new `charts` cases that failed first with
"is not a function"; tsc + svelte-check 0 / 0; biome 0 errors, 9 legacy warnings; harness 60
captures, 0 page errors, 0 layout failures, 0 height failures, index fresh 639 / 639;
`validate_palette.js … --ordinal` light `#4aaeff,#2890ff,#0073f7,#0058db` on `#ffffff` and
dark `#0055cd,#0072ec,#2190ff,#49b1ff` on `#1a1d21` — all checks pass). Reviewed at full
size: `overview-light-default`, `overview-dark-default`, `overview-light-table`,
`overview-dark-run-done`, `overview-light-empty`.
