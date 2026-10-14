---
milestone: M032
slice: S04
task: T02
project: llm-wiki
closed: 2026-10-14T14:48:00+02:00
verification: passed
---

# M032-S04-T02 -- Summary

## Commits

Committed together with this summary under the `M032-S04-T02:` ref — `git log --grep '^M032-S04-T02'`.

## Outcome

The status strip sits under the Ask bar: three equal `<button>` tiles. **Library** — the note
count, a 14-day sparkline of notes added (accent bars, today full, zero days as hairlines) and
"+15 today"; expanded: "+28 this week · updated 35m ago", the primary **Update knowledge**
(disabled while anything runs), a progress bar with "Updating · 3 of 12" while compiling and a
persistent "Up to date · took 2m" / "Update failed" line after; unreadable vault → "Can't read"
+ Open System Settings. **Health** — a ring in the worst severity's colour with the count (or
"OK") inside and the word beneath; expanded: each check's plain-English title with the engine
verb button (`Install`, `Rebuild`), running / done / failed state per row, fix hints as text, the
Update app row. **Capture** — two freshness meters (mic, system) decaying to empty at the zombie
threshold and the state word; expanded: ages + Start / Stop. Derivations (`status.ts`:
`addsPerDay`, `activity`, `healthSummary`, `captureSummary`) are pure and tested (8 cases incl.
a month boundary and the freshness math); primitives `ui/Sparkline`, `ui/Ring`, `ui/Meter` are
token-only SVG/CSS. The harness captures nine panel states light + dark (54 total), strict gate
clean.

## Deviations from plan

- First render overflowed the Capture tile: the Meter's inner `.row` class collided with the
  global `.row` layout class from tokens.css (min-height + divider). Renamed to `.line`;
  caught by the screenshot review, not by the gate (overflow was visible, not clipped).
- The library detail shows the compile button always (manual full update) — the counted
  "N new sources to add" suggestion still appears in Next-up (T03) from the engine.

## Follow-ups

- Global layout classes (`.row`, `.card`, `.caps`, `.num`) are a naming hazard for component
  classes; KNOWLEDGE note at S04 closeout (prefix component classes or avoid those names).

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` — passed (vitest 87
passed / 1 skipped incl. 8 `status` cases that failed first; svelte-check 0 / 0; biome 0
errors; 54 captures, 0 page errors, 0 layout failures). Reviewed `panel-dark-fresh`,
`panel-light-library-open`, `panel-dark-health-open`, `panel-light-capture-open`,
`panel-dark-running`, `panel-light-failed`, `panel-light-empty` at full size after the fix.
