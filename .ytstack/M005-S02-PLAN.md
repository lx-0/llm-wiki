---
milestone: M005
slice: S02
project: llm-wiki
created: 2026-05-15T17:00:00Z
status: planned
task_count: 3
completed_tasks: 1
---

# M005-S02 -- Slice Plan

**Goal:** `scripts/lint.py` enforces the two-layer shape for `type: person|project` pages and validates Obsidian-Tasks-compatible Action-Item syntax.

## Tasks

- [x] T01 -- Implement `check_two_layer_pages` (assert `## State` + `---` + `## Timeline` for `person|project`, Timeline reverse-chronological)
- [ ] T02 -- Implement `check_action_item_syntax` (validate `- [ ]`/`- [x]` lines, 📅 due format, optional ⏫ priority / 🔁 recurrence)
- [ ] T03 -- Test fixtures (valid + deliberately broken) + wire both checks into `wiki lint` CLI + `health.py`

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Lint emits actionable diagnostics on broken fixtures and stays silent on valid ones.

## Notes

(Add observations during slice execution.)
