---
milestone: M032
slice: S03
task: T03
project: llm-wiki
closed: 2026-10-14T22:05:00+02:00
verification: passed
---

# M032-S03-T03 -- Summary

## Commits

Committed together with this summary under the `M032-S03-T03:` ref — `git log --grep '^M032-S03-T03'`.

## Outcome

Browse and the triage window ("Inbox") are Svelte windows on the tokens; `browse.ts` /
`triage.ts` are deleted and the HTML shells are mount points. Browse keeps its shape — search,
type chips in canonical order, rows with the shared `TypeBadge` and a type-coloured edge, a
"N more — narrow the search" cap, a tabular footer of per-kind counts — on `filter.ts`
(`filterEntries`, `capRows`, `typeChips`, `typeCounts`, tested). Inbox keeps the grouped,
confidence-aware review on `groups.ts` (`groupRecords`: tasks → ideas → notes → other, unsure
first, newest first; `pendingCount`; `metaLine`, tested) with per-row Keep / Dismiss, batch
Keep all / Dismiss all (quiet) with a progress count, busy and error states, a "Show resolved"
switch and an honest empty state. Light mode works on both by construction — every colour is a
token (`ui/types.ts` resolves the type token; `TypeBadge` uses it too). Copy diet: the triage
sub-line and the two "Keep → …" group hints are gone, the window is called Inbox.

## Deviations from plan

- `metaLine` now names the file instead of a date folder for daily captures
  (`daily/2026-10-13/sessions.md` → "from sessions · 13 Oct"); the old code printed the date
  twice. Added as a test first.
- Group colours reuse the type wheel (tasks = project hue, ideas = map hue, notes = concept
  hue) rather than three new literals.

## Follow-ups

- The dead browse / triage / settings / onboarding CSS blocks in `index.css` go in T04.
- `main.ts` still titles the window "Triage" in its `BrowserWindow` options — rename to Inbox
  when S05-T02 touches the window table.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` + colour-literal audit —
passed (vitest 75 passed / 1 skipped incl. 9 new derivation cases that failed first;
svelte-check 0 warnings after adding the standard `line-clamp`; biome 0 errors; 36 captures,
0 page errors; 0 colour literals). Reviewed `browse-{light,dark}-default.png`,
`triage-{light,dark}-default.png`, `triage-light-empty.png` at full size — light mode is
legible everywhere (the T01-audit defect is closed), one primary per row, no overflow.
