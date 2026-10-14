---
milestone: M032
slice: S05
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 4
completed_tasks: 0
---

# M032-S05 -- Slice Plan

**Goal:** An Overview window with four real charts replaces Cockpit and Atlas, the app passes a blind learnability test at ≥ 8/10, the DMG is rebuilt, and every doc/decision artifact reflects the shipped state.

## Tasks

- [ ] T01 -- Overview window (`overview.html`, Svelte): notes added per day (30-day bars), type distribution (horizontal bars), health (ring + check list with verbs), capture timeline (24 h mic/system freshness strip), pending queue; SVG on tokens per the dataviz rules; fixtures + harness light/dark.
- [ ] T02 -- Cockpit + Atlas deleted (`cockpit.*`, `atlas.*`, `lib/types.ts`, their CSS, `main.ts` windows, IPC channels → `openOverview`); panel nav wired to Overview; renderer bundle entries updated.
- [ ] T03 -- Blind synthetic learnability panel (task-based, personas never told what each screen is) + one fix round; `npm run dmg` rebuilt; operator look at the installed app recorded in the summary.
- [ ] T04 -- Closeout: `desktop/README.md` rewritten short; DECISIONS entry (2026-06-24 locks reopened; Svelte 5 / Biome / Overview decisions); KNOWLEDGE (harness, Svelte + Forge, Biome partial `.svelte` coverage, TS 5 migration gotchas); `docs/PROCESS.md` note on the schema-2 JSON contract; engine CHANGELOG + version bump; `ytstack:reassess-roadmap`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
