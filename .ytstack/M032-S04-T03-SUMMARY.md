---
milestone: M032
slice: S04
task: T03
project: llm-wiki
closed: 2026-10-15T02:10:00+02:00
verification: passed
---

# M032-S04-T03 -- Summary

## Commits

Committed together with this summary under the `M032-S04-T03:` ref — `git log --grep '^M032-S04-T03'`.

## Outcome

**Next up** is the one list of things to do: `nextUp()` over the store's merged actions
(`actions()` folds doctor + menu + tools once, in the store, so every section reads the same
rows) keeps probe-raised rows in merge order — severity first, then the engine's counted
suggestions — and drops pure tools; five rows max, "Nothing to do — your wiki is current" when
the vault is quiet. Each row is a severity dot (column always reserved so titles line up), the
engine's plain-English title and its verb button; while that argv runs the button becomes an
inline bar with "2 of 3" (or indeterminate), and after `onRunDone` a done / failed pill stays
until the panel closes. **Recent** lists the five newest entries with the type badge, title and
age; an accent dot marks entries modified since the panel was last open (`recentSeenMs` in
localStorage, advanced on close). **Footer** is one 24 px row: `+ Add link` swaps the row for an
input + Add (YouTube → `ingest-youtube --url`, http(s) → `ingest-html`, else "Not a web page or
YouTube link" with Try again; adding / "Added — it shows up after the next update" / failed in
the same row), **Sources** and **Tools** open opaque popovers *over* the content (configured
collectors with Sync + a Sync all that queues them; the tool-backed actions with their verbs —
a tool the menu also raised keeps its counted title, never two phrasings for one argv), Quit at
the right. Escape and click-outside close them. The panel's requested height never changes
when the footer opens anything. Fresh panel: 639 px light and dark.

## Deviations from plan

- Sheets are popovers, not inline sections. The inline version pushed Sources (9 rows) to
  985 px — below the 640 px clamp, i.e. invisible without scrolling. A popover anchored above
  the footer bar keeps the trigger in view and the height fixed. The layout audit learned
  `[data-layer]`: text under an opaque layer is cut out of its boxes (covered, not
  overlapping), so the gate stays strict for everything else.
- Recent lost the planned type-coloured edge: the badge already carries the type, the edge
  was the same fact twice. The "new" dot stays.
- Sources rows have no icons (the plan said monochrome): a name + Sync button per row is the
  whole message; icons would be the third mark per row.
- `recentSeenMs` was silently dead on first render: `readSeen()` ran inside the module-level
  `$state` initializer and read a `const` declared *below* it — TDZ ReferenceError, swallowed
  by its own try/catch, so every launch looked "nothing new". Found by the harness (seeded
  localStorage, zero `.dot.new` in the DOM), fixed by declaring the helpers before `panel`.
- Fixture ages are assigned by rank now (one distinct age per entry) — the modulo mapping gave
  the five newest entries the same "12m ago", which read like a bug in every screenshot.
- Harness states added beyond the plan: `run-done` (done + failed pills) next to
  `run-progress`; the stub preload seeds `recentSeenMs` an hour back so two Recent rows show
  the dot.

## Follow-ups

- T04 swaps `index.html` to this mount and deletes `renderer.ts`; the old panel's `expanded`
  harness state goes with it.
- Header nav "Overview" still opens Cockpit until S05-T01 ships the Overview window.
- KNOWLEDGE (this commit): TDZ inside module-level `$state`, popover-vs-inline under a height
  clamp + the `[data-layer]` audit rule, and the global layout-class hazard from T02.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` — passed (vitest
94 passed / 1 skipped incl. 7 `sections` cases that failed first with "Cannot find module
'./sections'"; tsc + svelte-check 0 / 0; biome 0 errors, 12 pre-existing warnings in
cockpit/atlas/index.css; 64 captures, 0 page errors, 0 layout failures; `report.json`
panelHeights light-fresh 639, dark-fresh 639). Reviewed at full size: `panel-light-fresh`,
`panel-dark-fresh`, `panel-dark-sources-open`, `panel-light-tools-open`,
`panel-dark-tools-open`, `panel-light-add-open`, `panel-dark-add-open`,
`panel-dark-run-progress`, `panel-dark-run-done`.
