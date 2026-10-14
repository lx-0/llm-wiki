---
milestone: M032
slice: S04
task: T01
project: llm-wiki
closed: 2026-10-14T23:40:00+02:00
verification: passed
---

# M032-S04-T01 -- Summary

## Commits

Committed together with this summary under the `M032-S04-T01:` ref — `git log --grep '^M032-S04-T01'`.

## Outcome

The new panel exists as a second renderer page (`panel.html` → `src/windows/panel/`) beside
the shipped one, built under the strict layout gate. `store.svelte.ts` owns the panel state
(vault, entries, doctor, menu, listeners, inbox count, compile + run state, visibility) with one
parallel `refresh()`, the main-process event wiring (`connect()`: visibility → refresh and
clear results on close, compile/run progress + done, 5 s listener poll while visible) and the
actions (`runAction(argv)`, `startCompile()`, `toggleListener()`, `ask()`). `Header.svelte`:
logo, name, vault pill (opens Obsidian), settings gear, and a **labeled** nav — Overview ·
Notes · Inbox with the pending count — so the hint banner has no reason to exist. `Ask.svelte`:
the hero input + primary Ask, "Thinking…", answer card with copy (→ check for 1.5 s) and clear,
wikilink chips from `markdown.ts` (`renderAnswer`, tested) opening the file via a Svelte action.
`App.svelte` registers the `ResizeObserver` auto-fit. The harness captures `panel-*` in six
states, light + dark, strict.

## Deviations from plan

- `expanded` is not a panel state any more (no disclosures left to expand); T02/T03 add their
  own states if a section needs one.
- The harness's `asked` script now dispatches an `input` event after setting the value —
  framework bindings listen to `input`, the old DOM renderer read `.value` directly.
- Chip clicks use a `use:chipLinks` action instead of a template `onclick` on a `<div>`
  (svelte-check a11y rule); the nav item type is explicit (`badge: boolean` on every item).

## Follow-ups

- Overview still opens the old Cockpit window until S05 replaces it.
- T04 swaps `index.html` to this mount, deletes `renderer.ts` + `panel.html`.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` — passed (vitest
79 passed / 1 skipped incl. 4 `renderAnswer` cases that failed first; svelte-check 0 errors / 0
warnings; biome 0 errors; 48 captures, 0 page errors, 0 layout failures). Reviewed
`panel-light-fresh.png` and `panel-dark-asked.png`: labeled nav with the inbox badge, answer
card with chips and tools, nothing else on the screen yet.
