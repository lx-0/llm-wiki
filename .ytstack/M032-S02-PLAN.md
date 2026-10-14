---
milestone: M032
slice: S02
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 3
completed_tasks: 0
---

# M032-S02 -- Slice Plan

**Goal:** The engine owns the operator-facing vocabulary of every action: `wiki menu --json` and `wiki doctor --json` carry `schema`, `id`, `title`, `verb`, `group`, `argv`, the engine's maintenance tools are part of the same catalogue, and the desktop has one tested `Action` model that merges doctor + menu + tools without a hardcoded command list or regex rewriting.

## Tasks

- [ ] T01 -- Engine action catalogue: `scripts/core/actions.py` (one table: action id → title / verb / group / argv, plus the always-available tools lint/links/dedup/review-wiki/dream); `menu_context.build_suggestions` + `menu --json` emit `schema: 2` with `id`/`title`/`verb`/`group`/`argv` and a `tools` list; `doctor --json` checks gain `id`-keyed `title`/`verb`/`argv`; TUI output unchanged (operator terms stay on `label`); consumer grep (`menu.py`, `menu_context.py`, `core/health.py`, `doctor.py`, desktop `vault/*.ts`, tests); tests for the catalogue + both payloads.
- [ ] T02 -- Desktop `Action` model: `src/lib/actions.ts` — schema-2 types + `mergeActions(doctor, menu, tools)` (dedupe by id/argv, severity + group ordering, verb from the engine, running/result state keyed by argv) with vitest coverage over fixtures (duplicate dream across all three sources collapses to one row).
- [ ] T03 -- Main-process parsers + IPC: `vault/menu.ts`, `vault/doctor.ts` parse schema 2 (fallback-free: an old engine without `schema` yields `[]` + a logged warning, not a crash); IPC types in `vault/ipc.ts` updated; `ADVANCED_COMMANDS` retired in favour of the engine `tools` list; existing main-process tests updated.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `friendlyPending` / `pendingVerb` / `friendlyHealth` die with their last consumer (`renderer.ts`, `cockpit.ts`) in S04/S05 — no soft deprecation, no parallel path in the meantime.
- Engine CHANGELOG + version bump belong to S05 closeout (the JSON contract is an engine behaviour change).
