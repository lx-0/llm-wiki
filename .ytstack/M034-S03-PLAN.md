---
milestone: M034
slice: S03
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 4
completed_tasks: 0
---

# M034-S03 -- Slice Plan

**Goal:** `wiki hooks …` and `wiki skills …` run in Python. The installed hook commands are
byte-identical to what the bash wrote, and agent configs are merged with backups.
`lib/agents.sh`, `lib/hooks.sh` and `lib/skills.sh` are deleted.

## Tasks

- [ ] T01 -- The agent registry in Python: agent names and fields, scope dirs, presence and
  config paths, the hook-installed probe, `hook_cmd`, and the Claude / Codex / Gemini / Cursor
  payloads. Each payload is byte-identical to the bash `jq` output on the fixture (the S01
  goldens plus `test_hooks_merge.py`).
- [ ] T02 -- The merge into each agent's config, install one, uninstall one, and the `hooks
  install/uninstall/status` commands with the scope prompt. Other tools' hooks survive the
  merge, backups follow the existing rule, and parity holds on the fixture `HOME`. `wiki
  status` comes here as well (moved from S01-T05): a banner over S02's `config status` and
  this task's `hooks status`.
- [ ] T03 -- Skills in Python: the engine-owned check, the global-enable flag, registry
  add / remove, `skills install/uninstall/sync/status`, and the silent install / prune
  variants that `setup` and `update` call. Parity on the fixture `HOME`.
- [ ] T04 -- The three `lib/` files are deleted along with their `wiki` call sites. The oracle
  passes and the docs are updated. On scratch with a sandboxed `HOME`, an install → status →
  uninstall cycle runs per agent.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; hook commands in an
operator's agent configs would not change on reinstall.

## Notes

Never against the real `~` in tests or scratch runs: these commands write the operator's
agent configs. `~/.claude/settings.json` is off limits in a running session (CLAUDE.md § 1).
