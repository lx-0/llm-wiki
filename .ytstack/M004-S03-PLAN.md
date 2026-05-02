---
milestone: M004
slice: S03
project: llm-wiki
created: 2026-05-02T22:00:00Z
status: planned
task_count: 3
completed_tasks: 0
---

# M004-S03 — Dashboard auto-wiring for agent tasks

**Goal:** Every `prompts/agent_*.md` carrying `button:` frontmatter automatically gets a Dashboard button (Shell-Commands data + Meta-Bind def + inline reference) on `wiki seed`. Operators add a new task by dropping one .md file, running `wiki seed`, reloading Obsidian — done.

## What "done" looks like

- `lib/seed.sh` sweeps `prompts/agent_*.md` during `seed_vault_templates`, parses `button:` frontmatter, generates idempotent merges into `templates/.obsidian/plugins/obsidian-shellcommands/data.json` (under unique IDs prefixed `agent-`) and into `templates/dashboard.md` (hidden Meta-Bind defs + inline refs in a marked `<!-- agent buttons --> ... <!-- /agent buttons -->` region).
- Re-running `wiki seed` is idempotent — second run produces no diff.
- Removing a button: delete the agent prompt file, run `wiki seed --prune-agent-buttons` (new flag), entries get cleaned out. Default seed never deletes (additive — same convention as community-plugins.json).
- After S03 closes, the manual button wiring done in S02 gets auto-regenerated identically — verified by diff.

## Tasks

- [ ] T01 — Frontmatter sweep helper. Python script `scripts/agent_buttons.py` walks `prompts/agent_*.md`, parses each `button:` frontmatter, returns a list of `{id, label, style, tooltip, shell_command_id, command}` dicts. Errors surfaced as warnings, not crashes (tasks without `button:` are fine — just skipped).
- [ ] T02 — Shell-commands seed merge. Extend `lib/seed.sh` with `_merge_shell_commands_for_agents()` that calls T01 helper, computes the JSON entries for each declared button, deep-merges into `templates/.obsidian/plugins/obsidian-shellcommands/data.json` via jq. Idempotent on re-run.
- [ ] T03 — Dashboard inline-ref auto-render. Same sweep produces (a) hidden `meta-bind-button` blocks at the end of `templates/dashboard.md` inside a marked region, (b) inline `` `BUTTON[id]` `` refs inside a region near the existing Capture/Run sections. Region markers: `<!-- agent-buttons:begin -->` / `<!-- agent-buttons:end -->`. `wiki seed` rewrites the region; nothing outside is touched.

## Files touched

- NEW: `scripts/agent_buttons.py`
- MODIFY: `lib/seed.sh` (new helper + call from `seed_vault_templates`), `templates/dashboard.md` (insert region markers in Run section), `wiki` (`--prune-agent-buttons` flag on seed)

## Verification

```bash
# After dropping prompts/agent_summarize-day.md (already from S02):
./wiki seed
# Expect: ✓ shell-commands.json — added agent-summarize-day
# Expect: ✓ dashboard.md — agent-buttons region updated (1 button)

# Idempotency:
./wiki seed
# Expect: info: agent buttons already up to date

# In lxw vault: reload, see "📅 Summarize day" button in Run row.
```

## Out of scope (deferred)

- Auto-pruning by default (S03 ships --prune-agent-buttons as opt-in flag; default = additive)
- Per-button cooldown / piggyback integration → backlog
- Auto-wired buttons in QuickAdd / Capture rows (S03 ships Run-row only)
