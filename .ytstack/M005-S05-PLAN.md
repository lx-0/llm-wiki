---
milestone: M005
slice: S05
project: llm-wiki
created: 2026-05-15T17:00:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M005-S05 -- Slice Plan

**Goal:** Extend the existing Obsidian dashboard (M003-S01) with a Personal Tasks pane and ship a cross-entity Inbox MOC that survives `wiki seed`.

## Tasks

- [ ] T01 -- Add Dataview `TASK WHERE !completed` block to dashboard, filtered to `knowledge/people/` + `knowledge/projects/`, grouped by Today / Overdue / This Week
- [ ] T02 -- Add open-commitments stat card paired with context stat (e.g. "entities with action items" or "commitments captured this week"), following honesty + positive-framing rule
- [ ] T03 -- Create `knowledge/MOCs/inbox-tasks.md` standalone cross-entity inbox MOC; dashboard pane links to it
- [ ] T04 -- Update `templates/.obsidian/` + dashboard template so the pane survives `wiki seed --force` (cssclasses-via-frontmatter convention)

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Manual Obsidian render confirms the pane shows real action items from S03 extraction; `wiki seed --force` does not blow away the customisation.

## Notes

(Add observations during slice execution.)
