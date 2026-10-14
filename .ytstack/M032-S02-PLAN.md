---
milestone: M032
slice: S02
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 4
completed_tasks: 3
---

# M032-S02 -- Slice Plan

**Goal:** The engine owns the operator-facing vocabulary of every action: `wiki menu --json` and `wiki doctor --json` carry `schema`, `id`, `title`, `verb`, `group`, `argv`, the engine's maintenance tools are part of the same catalogue, and the desktop has one tested `Action` model that merges doctor + menu + tools without a hardcoded command list or regex rewriting.

## Tasks

- [x] T01 -- Engine action catalogue + menu JSON: `scripts/core/actions.py` (one table: action id → plain-English title (singular/plural), verb, group, argv; plus the always-available tools lint / links / dedup / review-wiki / dream); `menu_context.build_suggestions` keys every probe on a catalogue id and emits `id`/`title`/`verb`/`group`/`argv` (+ `label` for the TUI); `menu --json` gains `schema: 2` + `tools`; `menu.py` consumes `argv`; tests for the catalogue + payload.
- [x] T02 -- Doctor JSON: `CheckResult` gains optional `title` (plain-English phrasing next to the check that produces the jargon) and `to_json` emits `schema: 2`, `title` (defaults to `message`), `verb` (from the catalogue by `dispatch_args[0]`); `doctor.py` wraps the payload with `schema`; TUI untouched; tests updated (`test_health.py`, `test_doctor.py`, `test_cli_json_seams.py`).
- [x] T03 -- Desktop `Action` model: `src/lib/actions.ts` — schema-2 types + `mergeActions(doctor, menu, tools)` (dedupe by argv, severity + group ordering, verb from the engine, running/result state keyed by argv) with vitest coverage over fixtures (duplicate dream across all three sources collapses to one row).
- [ ] T04 -- Main-process parsers + IPC: `vault/menu.ts`, `vault/doctor.ts` parse schema 2 (an engine payload without `schema: 2` yields `[]` + a logged warning, not a crash); IPC types in `vault/ipc.ts` updated; `ADVANCED_COMMANDS` retired in favour of the engine `tools` list; harness fixtures moved to schema 2; existing main-process tests updated.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `friendlyPending` / `pendingVerb` / `friendlyHealth` die with their last consumer (`renderer.ts`, `cockpit.ts`) in S04/S05 — no soft deprecation, no parallel path in the meantime.
- Engine CHANGELOG + version bump belong to S05 closeout (the JSON contract is an engine behaviour change).
