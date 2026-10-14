---
milestone: M032
slice: S05
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 6
completed_tasks: 4
---

# M032-S05 -- Slice Plan

**Goal:** An Overview window with four real charts replaces Cockpit and Atlas, the app passes a blind learnability test at ≥ 8/10, the DMG is rebuilt, and every doc/decision artifact reflects the shipped state.

## Tasks

- [x] T01 -- Capture timeline source: `listeners.timeline(id, hours)` — hourly mic/system chunk counts from the listener's sqlite (`audio_chunks` timestamps, read-only) bucketed by a pure, tested function; IPC contract + preload + main handler; stub preload + fixture with a realistic day shape.
- [x] T02 -- Overview window scaffold (`overview.html`, Svelte): `openOverview` IPC + window + panel nav wired, hero note count + stat tiles (updated today / this week / inbox / issues), the 30-day "notes updated per day" column chart with per-bar tooltips (shared `ui/tip` action), activity derivations moved to `lib/activity.ts` and shared with the panel (label honesty: "updated", not "added"); harness surface light/dark under the strict gate.
- [x] T03 -- Overview charts completed: notes by type (horizontal bars, one hue, type badges as labels), capture — last 24 h (2 × 24 heat strip from T01, one-hue lightness steps validated as an ordinal ramp), health (ring + check list with verbs), next up (merged action list with verbs); a table view toggle rendering every chart's twin; empty states; harness states.
- [x] T04 -- Cockpit + Atlas deleted (`cockpit.*`, `atlas.*`, `lib/types.ts`, `index.css`, `main.ts` windows + IPC channels); Triage window titled Inbox with a theme-aware background; renderer bundle entries updated.
- [ ] T05 -- Blind synthetic learnability panel (task-based, personas never told what each screen is) + one fix round; `npm run dmg` rebuilt; operator look at the installed app recorded in the summary.
- [ ] T06 -- Closeout: `desktop/README.md` rewritten short; DECISIONS entry (2026-06-24 locks reopened; Svelte 5 / Biome / Overview decisions); KNOWLEDGE (harness, Svelte + Forge, Biome partial `.svelte` coverage, TS 5 migration gotchas); `docs/PROCESS.md` note on the schema-2 JSON contract; engine CHANGELOG + version bump; smoke page deleted; `ytstack:reassess-roadmap`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- 2026-10-15 (before T02): the Overview window split in two — T02 ships the window with its wiring, stat row and first chart (a page no nav opens is not shippable, and that alone is ~15 small files); T03 adds the remaining three charts, the action list and the table view. Six tasks now.
- 2026-10-15 (before T01): re-sliced from 4 to 5 tasks. The "capture timeline (24 h)" chart has no data behind it — listener status only knows the newest chunk per channel — so the hourly history becomes its own task (sqlite read + IPC + fixtures) ahead of the window; Cockpit/Atlas deletion, learnability and closeout shift to T03–T05. The smoke page deletion moves into the closeout task explicitly.
