---
milestone: M032
slice: S05
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 5
completed_tasks: 1
---

# M032-S05 -- Slice Plan

**Goal:** An Overview window with four real charts replaces Cockpit and Atlas, the app passes a blind learnability test at ≥ 8/10, the DMG is rebuilt, and every doc/decision artifact reflects the shipped state.

## Tasks

- [x] T01 -- Capture timeline source: `listeners.timeline(id, hours)` — hourly mic/system chunk counts from the listener's sqlite (`audio_chunks` timestamps, read-only) bucketed by a pure, tested function; IPC contract + preload + main handler; stub preload + fixture with a realistic day shape.
- [ ] T02 -- Overview window (`overview.html`, Svelte): hero note count + stat tiles, notes updated per day (30-day columns), type distribution (horizontal bars, one hue, type badges as labels), capture timeline (2 × 24 heat strip from T01), health (ring + check list with verbs), pending queue; tooltips + a table view; SVG on tokens per the dataviz rules; `openOverview` IPC + panel nav wired; fixtures + harness light/dark under the strict gate.
- [ ] T03 -- Cockpit + Atlas deleted (`cockpit.*`, `atlas.*`, `lib/types.ts`, `index.css`, `main.ts` windows + IPC channels); Triage window titled Inbox with a theme-aware background; renderer bundle entries updated.
- [ ] T04 -- Blind synthetic learnability panel (task-based, personas never told what each screen is) + one fix round; `npm run dmg` rebuilt; operator look at the installed app recorded in the summary.
- [ ] T05 -- Closeout: `desktop/README.md` rewritten short; DECISIONS entry (2026-06-24 locks reopened; Svelte 5 / Biome / Overview decisions); KNOWLEDGE (harness, Svelte + Forge, Biome partial `.svelte` coverage, TS 5 migration gotchas); `docs/PROCESS.md` note on the schema-2 JSON contract; engine CHANGELOG + version bump; smoke page deleted; `ytstack:reassess-roadmap`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- 2026-10-15 (before T01): re-sliced from 4 to 5 tasks. The "capture timeline (24 h)" chart has no data behind it — listener status only knows the newest chunk per channel — so the hourly history becomes its own task (sqlite read + IPC + fixtures) ahead of the window; Cockpit/Atlas deletion, learnability and closeout shift to T03–T05. The smoke page deletion moves into the closeout task explicitly.
