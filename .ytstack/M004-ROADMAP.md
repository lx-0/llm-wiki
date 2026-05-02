---
milestone: M004
project: llm-wiki
size: M
created: 2026-05-02T21:50:00Z
status: done
total_slices: 3
completed_slices: 3
---

# M004 Roadmap

**Goal:** Operators add new agentic tasks by dropping a single `prompts/agent_<id>.md` markdown file — no engine code changes.

**Exit criteria:**

- `scripts/agent_task.py` reads task spec from prompt frontmatter, spawns Claude Agent SDK with declared model + tools + permission + max_turns + cwd
- `wiki agent <id> | --list | --dry-run` CLI works
- `summarize-day` ships as first concrete task: appends `## Summary` to `daily/<today>.md`
- Dashboard buttons auto-wired via `wiki seed` (shell-commands data.json merge + hidden Meta-Bind defs + inline `BUTTON[id]` refs)
- Tests for frontmatter parser + CLI dispatch + summarize-day smoke
- Docs: PROCESS.md §14, KNOWLEDGE.md, README, AGENTS.md

## Slices

Slice detail lives in per-slice `M004-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 — Core framework: `scripts/agent_spec.py` (parser + dataclass + 17 tests), `scripts/agent_task.py` (SDK runner), `wiki agent` CLI dispatcher
- [x] S02 — First concrete task: `prompts/agent_summarize-day.md` (Haiku, Read/Edit/Write), 3 smoke tests, manually-wired Dashboard button
- [x] S03 — Dashboard auto-wiring: `scripts/agent_buttons.py` (discovery + region-rewrite), `lib/seed.sh:_merge_agent_shell_commands` (jq additive merge), `lib/seed.sh:_rewrite_dashboard_agent_buttons` (marker-based, idempotent)

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
