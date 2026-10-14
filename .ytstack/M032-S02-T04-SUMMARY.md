---
milestone: M032
slice: S02
task: T04
project: llm-wiki
closed: 2026-10-14T19:45:00+02:00
verification: passed
---

# M032-S02-T04 -- Summary

## Commits

Committed together with this summary under the `M032-S02-T04:` ref — `git log --grep '^M032-S02-T04'`.

## Outcome

The desktop reads the engine's schema-2 payloads and nothing else: `parseMenu` returns
suggestions with `id`/`title`/`verb`/`group`/`argv`/`priority` plus the `tools` list,
`parseDoctor` returns checks with `title` + `verb`; both refuse an unknown schema with empty
lists and a `console.warn` instead of guessing. `ADVANCED_COMMANDS` and the per-command
`run(id)` catalogue are gone (`EngineCommandId` is just `update`; everything else runs through
`runArgs(argv)`); `lib/pending.ts` (`friendlyPending` / `pendingVerb`) and `friendlyHealth`
are deleted. The current panel and cockpit render `title` / `verb` and dispatch `argv` — the
Advanced disclosure now lists the engine's tools with their own verbs, health rows carry the
engine verb ("Install", "Rebuild") instead of a hardcoded "Fix", and the two sentence-tooltips
on those buttons are gone. Harness fixtures are schema 2.

## Deviations from plan

- The first green run hid a test bug: `payload(checks, schema = 2)` turned the "unknown schema"
  case's `undefined` into 2 via the default parameter; the case now passes `null`.
- Health-row buttons also switched to the engine verb (one line) — not in the plan, but the
  "one verb" principle made the hardcoded "Fix" next to "Install" look wrong immediately.

## Follow-ups

- S03/S04 build the new windows on `lib/actions.ts` + these parsers; the renderer/cockpit edits
  here are throwaway bridges so the app stays usable.
- S02 complete → `ytstack:reassess-roadmap`.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` — passed (typecheck +
svelte-check silent, vitest 63 passed / 1 skipped, biome 0 errors, 30 captures, 0 page errors).
`index-dark-expanded.png` shows the engine titles in Health ("Session capture isn't installed",
"The note index is out of sync"), What's pending ("3 new captures to sort" / Sort …) and the
tools under Advanced with their verbs. TDD: both parser test files failed (6 cases) before the
parsers changed.
