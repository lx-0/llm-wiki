---
milestone: M032
slice: S03
task: T02
project: llm-wiki
closed: 2026-10-14T21:20:00+02:00
verification: passed
---

# M032-S03-T02 -- Summary

## Commits

Committed together with this summary under the `M032-S03-T02:` ref — `git log --grep '^M032-S03-T02'`.

## Outcome

Settings and Onboarding are Svelte windows on the token system (`src/windows/settings/`,
`src/windows/onboarding/`; `settings.html` / `onboarding.html` are mount points; the old
`settings.ts` / `onboarding.ts` are deleted). Settings: a Library card (name · count, truncated
mono path, "Open in Obsidian") and a Preferences card of label + value rows — Start at login
(switch), File access (Granted / Not granted + "Open System Settings" only when missing), Screen &
audio capture (Recording / Paused / Check / Not configured, coloured by state). Onboarding: logo,
title, one sentence of purpose, one card of rows — Your library (value), Grant file access (only
while unreadable: Re-check + Open Settings), Background capture (switch + the one consent
sentence), Start at login — and the single primary "Get started". The two status derivations
live in `labels.ts` (tested). Harness: settings default / no-access, onboarding default /
no-access / empty, light + dark (36 captures).

## Deviations from plan

- No numbered step circles; the rows read as a sequence without them.
- The "no library at all" onboarding branch (`vault === null`) renders "None yet — set one up
  with the wiki CLI" but has no fixture state yet (the `empty` fixture keeps a library with 0
  notes); add a `no-library` state when the panel's empty state is designed in S04.

## Follow-ups

- The Settings window is now ~240 px of content in a 400 px frame — shrink the
  `BrowserWindow` height in `main.ts` when S05-T02 touches the window table.
- The settings / onboarding CSS blocks in `index.css` are dead and go in T04.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` + colour-literal audit —
passed (vitest 66 passed / 1 skipped incl. the 4 new label cases, which failed first; biome 0
errors; 36 captures, 0 page errors; 0 colour literals in the two windows). Reviewed
`settings-{dark-default,light-no-access}.png` and `onboarding-{light-default,dark-no-access,
light-empty}.png` at full size: one primary per view, no overflow, values readable in both
schemes.
