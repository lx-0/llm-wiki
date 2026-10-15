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

**Goal:** `wiki hooks …`, `wiki skills …` and `wiki status` run in Python. The installed hook
commands are byte-identical to what the bash wrote, and agent configs are merged with backups.
`lib/agents.sh`, `lib/hooks.sh` and `lib/skills.sh` are deleted. So is `lib/config.sh`, whose
last callers were skills' `config_get` and `cmd_status` (reassessed after S01).

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

  **Fix first, in the bash, then record.** Three defects; the oracle holds the wrong behaviour
  of two of them today:
  1. **A payload that cannot be built** (found in S02-T05's end-to-end run). When an agent's
     `jq` fails, the installer says `✗ unknown agent: claude`, writes nothing, and still ends
     `✓ Done. Restart agent CLIs…` with exit 0.
  2. **`hooks uninstall` removes nothing from a current install** (found planning S03; the
     `hooks-uninstall` golden recorded it). Its filter matches `\.wiki/hooks/`, a third copy
     of the hook-command grammar, which drifted: today's command is
     `cd '<vault>/.wiki' && uv run python hooks/…`. The settings stay untouched, a backup is
     made, and it reports `✓ claude (user): removed wiki hooks`.
  3. **For Cursor's bare `{type, command}` entries,** the same filter keeps only entries that
     carry a `.hooks` array, so it would drop the operator's other Cursor hooks too.

  The port uses **one** grammar (`hooks_installed`'s / `_WIKI_HOOK_CMD_RE`) for status, merge
  and uninstall, names real failures, and exits non-zero on them. The bash gets the same
  fixes before the oracle re-records `hooks-uninstall` and adds an uninstall case that keeps
  another tool's hook.
- [ ] T03 -- Skills in Python: the engine-owned check, the global-enable flag, registry
  add / remove, `skills install/uninstall/sync/status`, and the silent install / prune
  variants that `setup` and `update` call. Parity on the fixture `HOME`.
- [ ] T04 -- The three `lib/` files are deleted along with their `wiki` call sites, and so is
  `lib/config.sh` (its last callers, `config_get` in skills and `config_cmd_status` in
  `cmd_status`, are ported in T02 / T03). `lib/ui.sh` stays for `cmd_update`'s stash prompt
  until S05. The oracle passes and the docs are updated. On scratch with a sandboxed `HOME`,
  an install → status → uninstall cycle runs per agent.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; hook commands in an
operator's agent configs would not change on reinstall.

## Notes

Never against the real `~` in tests or scratch runs: these commands write the operator's
agent configs. `~/.claude/settings.json` is off limits in a running session (CLAUDE.md § 1).
