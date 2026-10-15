---
milestone: M034
slice: S03
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 7
completed_tasks: 6
---

# M034-S03 -- Slice Plan

**Goal:** `wiki hooks …`, `wiki skills …` and `wiki status` run in Python. The installed hook
commands are byte-identical to what the bash wrote, and agent configs are merged with backups.
`lib/agents.sh`, `lib/hooks.sh` and `lib/skills.sh` are deleted. So is `lib/config.sh`, whose
last callers were skills' `config_get` and `cmd_status` (reassessed after S01).

## Tasks

- [x] T01 -- The agent registry in Python: agent names and fields, scope dirs, presence and
  config paths, the hook-installed probe, `hook_cmd`, and the Claude / Codex / Gemini / Cursor
  payloads. Each payload is byte-identical to the bash `jq` output on the fixture (the S01
  goldens plus `test_hooks_merge.py`).
- [x] T02 -- **Fix the hooks commands in the bash, then record them** (split from the port
  after T01: the fixes, their records and a release fill one task, the port another). Three
  defects; the oracle holds the wrong behaviour of two of them today:
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

  The bash uses **one** grammar (T01's, the probe's union) for the probe, the merge and the
  uninstall, names real failures, and exits non-zero on them. The oracle then re-records
  `hooks-uninstall` and adds the cases that pin the fixes: an uninstall that keeps another
  tool's hook (a Claude group and a Cursor bare entry), a payload that cannot be built, and
  an uninstall with nothing to remove. Release 0.7.16.
- [x] T03 -- **One backup helper** (T02 follow-up; split from the port after T02). The port
  needs T02's rule: never over an earlier backup, and a clash takes `-2`.
  `core/frontmatter.backup` (correct / take / correct_apply) has the same to-the-second
  overwrite flaw, and `dedup.py` hand-rolls a copy. `core/backup.py` becomes the one helper
  for all of them, with a seam guard against a second `.bak.` writer.
- [x] T04 -- **The merge and the uninstall as pure functions** in `core/agents.py` (split
  from the port after T03): `merge(config, payload)` and `without_wiki_hooks(config)`.
  Rendered, they match the bash `jq` byte for byte on T02's shapes: Claude groups, Cursor
  bare entries, other tools' hooks and keys, groups and events the removal empties. Nothing
  calls them yet, so no release.
- [x] T05 -- **Port** `wiki hooks install/uninstall/status` with the scope prompt, and `wiki
  status` (moved from S01-T05: a banner over S02's `config status` and the hooks table), at
  parity with T02's record. Backups go through T03's helper, and the hook commands stay
  byte-identical. `setup`'s hooks step runs in-process. The probe decision (T01 follow-up)
  ships here, as a decided difference for `hooks status` and doctor alike: walk the hook
  entries instead of grepping the config's text.
- [x] T06 -- Skills in Python: the engine-owned check, the global-enable flag, registry
  add / remove, `skills install/uninstall/sync/status`, and the silent install / prune
  variants that `setup` and `update` call. Parity on the fixture `HOME`.
- [ ] T07 -- The three `lib/` files are deleted along with their `wiki` call sites, and so is
  `lib/config.sh` (its last callers, `config_get` in skills and `config_cmd_status` in
  `cmd_status`, are ported in T05 / T06). `lib/ui.sh` stays for `cmd_update`'s stash prompt
  until S05. The oracle passes and the docs are updated. On scratch with a sandboxed `HOME`,
  an install → status → uninstall cycle runs per agent.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; hook commands in an
operator's agent configs would not change on reinstall.

## Notes

Never against the real `~` in tests or scratch runs: these commands write the operator's
agent configs. `~/.claude/settings.json` is off limits in a running session (CLAUDE.md § 1).
