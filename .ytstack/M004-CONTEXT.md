---
milestone: M004
project: llm-wiki
created: 2026-05-02T21:50:00Z
size: M
---

# M004 — Context

## Goal

Operators add new agentic tasks (LLM-driven jobs over the vault) by dropping a single `prompts/agent_<id>.md` file — no engine code changes required. Tasks are runnable from the CLI (`wiki agent <id>`) and from the Dashboard via auto-wired buttons.

## Exit criteria

- `scripts/agent_task.py` reads a task spec from `prompts/agent_<id>.md` (YAML frontmatter declares `model`, `allowed_tools`, `permission_mode`, `max_turns`, `cwd`, optional `button`; body is the prompt) and spawns Claude Agent SDK accordingly. Result text persisted to `.wiki/logs/agent-<id>-<ts>.log`.
- `wiki agent <id>` runs a single task. `wiki agent --list` enumerates available tasks with title + button presence. `wiki agent <id> --dry-run` prints the resolved spec without spawning.
- First concrete task `summarize-day` ships and works: reads `daily/<today>.md`, appends or updates a `## Summary` block at the top with 3–5 bullets + open questions + projects touched. Cheap model (Haiku).
- Dashboard auto-wires buttons: every `prompts/agent_*.md` carrying `button:` frontmatter (label / style / shell_command_id) gets an entry merged into `templates/.obsidian/plugins/obsidian-shellcommands/data.json` and a hidden Meta-Bind button-definition appended to `templates/dashboard.md` during `wiki seed`. Inline `` `BUTTON[id]` `` references for the auto-generated buttons land in a clearly-marked Run-Agents section.
- Tests cover: (a) frontmatter parser handles all spec fields + invalid spec rejection, (b) `wiki agent --list` finds task files, (c) `summarize-day` smoke run on a fixture daily-log writes a Summary block.
- Docs: PROCESS.md §14 "Agent Tasks" (mermaid + spec table + edge cases), KNOWLEDGE.md learning entry on the prompt-as-config pattern, README CLI section gains `wiki agent ...`, AGENTS.md (engine) describes the new convention.

## Size

M — 3 slices planned. See `M004-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-05-02: chose combined Option 2+3 from triage (generic framework + ship summarize-day as the first concrete task) over either pure-bespoke (per-task Python scripts → script explosion) or pure-framework (plumbing without users). Prompt-as-config means the operator's editing surface is a single `.md` file per task.
- 2026-05-02: tasks live in `prompts/agent_*.md` (not a separate `agents/` dir) so they sit alongside the existing prompt-rendering convention (`prompts.py` already does `${var}` substitution). New agent tasks reuse that pipeline.
- 2026-05-02: Dashboard button auto-wiring runs at `wiki seed` (idempotent merge), not at runtime (`wiki agent --list` is purely read-only). Operators ship the engine, then `wiki seed` to refresh button definitions.

## Open questions

- Per-task scheduling: should agent tasks be invokable as piggybacks (analog to scan-screenshots etc.) on a cooldown? Defer to S03 or backlog.
- Task argument injection: `--var key=value` substitution into the prompt body (analog to existing `prompts.py:render`) — design in S01 frontmatter spec.
- Concurrency: two operators triggering the same agent task in parallel — file-lock per-task in `.wiki/state/agent-locks/`? Probably out of scope for M004 (single-operator vaults).
