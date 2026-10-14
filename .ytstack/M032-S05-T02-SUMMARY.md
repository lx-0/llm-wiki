---
milestone: M032
slice: S05
task: T02
project: llm-wiki
closed: 2026-10-15T04:45:00+02:00
verification: passed
---

# M032-S05-T02 -- Summary

## Commits

Committed together with this summary under the `M032-S05-T02:` ref — `git log --grep '^M032-S05-T02'`.

## Outcome

The panel's "Overview" nav item opens a real window: `app.openOverview()` → a 900 × 700
singleton (min 720 × 560, theme-aware background, Browse's loading pattern) rendering
`overview.html` → `src/windows/overview/App.svelte`. The page is header (logo · Overview ·
vault pill → Obsidian), a hero figure (note count, 48 px, proportional figures, "notes"
beneath), four stat tiles (Updated today · This week · Inbox · Issues) and the first chart:
"Notes updated per day, last 30 days" — `ui/Columns.svelte`, a single-series column chart on
tokens (bars ≤ 24 px with a 2 px surface gap, 4 px rounded caps square at the baseline,
hairline gridlines at 0 and the clean maximum, Monday + Today ticks, today's value as the one
direct label, every slot a keyboard-reachable hit target with a tooltip "Wed 14 Oct · 4
notes"). `ui/tip.ts` is the window-wide tooltip action (one `<div role="tooltip">`, hover +
focus, Escape hides, the text doubles as `aria-label`). The derivations are pure and tested:
`dayAxis` (ISO keys + names, ticks), `columnScale` (1·2·5 × 10ⁿ maximum), `statTiles`; the
day-counting moved out of the panel into `lib/activity.ts` (`countPerDay`, `activity`,
`daysAgo`) so both windows count the same way, and the panel's sparkline now says "updated"
(mtimes say touched, not created). "Can't read your library" + Open System Settings when the
vault is blocked. Harness: `overview` is a strict surface, light + dark, default / empty /
no-access.

## Deviations from plan

- The axis grew a rule the plan did not have: a Monday within three days of today loses its
  tick. The first render put "12 Oct" under "Today" two slots apart — the layout gate caught
  it (240 px² text overlap on all four default/empty captures) before any eye did.
- Keyboard focus on a bar is a `<g tabindex="0">`; svelte-check's a11y rule objects to a
  focusable non-interactive element, so the line carries a `svelte-ignore` with the reason
  (the data point's tooltip is its value — the dataviz interaction rule).
- The chart grid is two columns with one card in this task, by design (T03 fills the rest);
  the shipped intermediate state has empty space on the right.

## Follow-ups

- T03: notes by type, capture heat strip (ordinal ramp validated from the rendered colours),
  health, next up, table-view toggle, empty states.
- A `hover` harness state (dispatch `pointerenter` on a bar) would put the tooltip in a
  screenshot; not added — the tooltip is positioned by DOM measurement that the audit
  already exercises through the rendered `.tip`-less page. Revisit if a tooltip ever
  misplaces.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots …` — passed
(vitest 107 passed / 2 skipped incl. 6 `charts` + 4 `activity` cases that failed first with
"Cannot find module"; the Monday-clearance case failed first with `"12 Oct"` present; tsc +
svelte-check 0 / 0; biome 0 errors, 9 legacy warnings; harness 56 captures, 0 page errors,
0 layout failures, 0 height failures, index fresh 639 / 639). Palette on record:
`validate_palette.js "#007aff" --mode light --surface "#f6f6f8"` and `"#0a84ff" --mode dark
--surface "#1c1c1e"` — all checks pass. Reviewed at full size: `overview-light-default`,
`overview-dark-default`, `overview-light-empty`, `overview-light-no-access`.
