---
milestone: M004
slice: S02
project: llm-wiki
created: 2026-05-02T22:00:00Z
status: planned
task_count: 3
completed_tasks: 0
---

# M004-S02 — `summarize-day` agent task

**Goal:** First concrete agent task ships and works on a real daily log: appends a `## Summary` block to `daily/<today>.md` with 3–5 bullets + open questions + projects touched. Cheap model.

## What "done" looks like

- `prompts/agent_summarize-day.md` exists with full frontmatter (label, model: claude-haiku-4-5, allowed_tools: [Read, Edit], permission_mode: acceptEdits, button: present).
- `wiki agent summarize-day` runs end-to-end on the user's lxw vault and produces a meaningful summary block.
- Smoke test: pytest fixture creates `daily/2026-05-02.md` with sample log, runs the agent against it (mocked SDK that just appends a deterministic string), verifies the result.
- Manual Dashboard button: a new entry in `templates/.obsidian/plugins/obsidian-shellcommands/data.json` wires `./.wiki/wiki agent summarize-day`. A new `meta-bind-button` block + inline `BUTTON[btn-summarize-day]` ref in `templates/dashboard.md` (in S03 this becomes auto-generated).

## Tasks

- [ ] T01 — Write `prompts/agent_summarize-day.md`. Frontmatter declares the spec (Haiku model for cost, Read+Edit tools, button label "📅 Summarize day", style primary, shell_command_id `agent-summarize-day`). Body instructs the agent to read `daily/${today}.md`, find or create a `## Summary` block at the top, fill 3–5 terse bullets + open questions + projects touched, do not rewrite the rest.
- [ ] T02 — Smoke test for summarize-day. `tests/test_summarize_day.py` creates a fixture daily-log, calls `agent_task.run("summarize-day", dry_run=False)` with mocked SDK that returns a fake summary, asserts the file gets a Summary block prepended.
- [ ] T03 — Manual Dashboard wiring. Append new entry to `templates/.obsidian/plugins/obsidian-shellcommands/data.json` (`agent-summarize-day` → `./.wiki/wiki agent summarize-day`). Append a hidden `meta-bind-button` block + an inline `` `BUTTON[btn-summarize-day]` `` reference to `templates/dashboard.md` Run section (placed beside the existing Compile/Lint buttons). Verify in lxw vault by reload.

## Files touched

- NEW: `prompts/agent_summarize-day.md`, `tests/test_summarize_day.py`
- MODIFY: `templates/.obsidian/plugins/obsidian-shellcommands/data.json`, `templates/dashboard.md`

## Verification

```bash
cd .wiki && uv run pytest tests/test_summarize_day.py -v
./wiki agent summarize-day --dry-run    # prints resolved spec
./wiki agent summarize-day              # actual run on user's daily/<today>.md
```

## Out of scope (deferred)

- Auto-wiring the button (manual in S02; S03 sweeps `prompts/agent_*.md` for button: frontmatter)
- Other agent tasks (review-mocs, weekly-digest, extract-todos) — backlog or future milestone
