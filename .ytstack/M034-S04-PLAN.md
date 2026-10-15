---
milestone: M034
slice: S04
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 4
completed_tasks: 0
---

# M034-S04 -- Slice Plan

**Goal:** `wiki seed` runs in Python, with every template merge at parity on the fixture vault
and on a copy of the live `.obsidian/`; `lib/seed.sh` (708 lines) is deleted.

## Tasks

- [ ] T01 -- The seed core:
  - the template walk and its skip rules;
  - semantic file equivalence (what `jq -S` gave, in `json`);
  - the custom overlay: compute, apply, extract into `.wiki/custom/`.

  Open question 4 is decided in DECISIONS. Unit tests run on fixture templates.
- [ ] T02 -- The special merges:
  - community plugins, `appearance.json`, the `.env` example;
  - meta-bind data, agent shell commands, the dashboard agent buttons.

  Each at parity with the bash on the fixture and on a copy of the live vault's `.obsidian/`
  (the real data shape — arrays included; read-only source, copied to a tmp dir).
- [ ] T03 -- The `seed` command (`--force`, `--check`, `seed extract-custom`). The `--check`
  drift report uses the engine-relevant subset if the port makes that cheap
  (`backlog/seed-semantic-diff.md`). `test_seed_preserves_caches.py` is kept green.
- [ ] T04 -- `lib/seed.sh` is deleted along with its `wiki` call sites. The oracle passes, the
  docs are updated, and a scratch `wiki seed` and `wiki seed --force` match the bash goldens.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; no bash left for seeding.

## Notes

The memory "round-trip on the real data shape before a live `--force`" applies: the live
vault's `.obsidian/` JSON carries arrays and plugin data the fixture may not. Copy it and
compare; never write the live vault.

**What S03 taught for this slice** (reassessment after S03, outcome A: the slice order
holds; these refine the tasks when they are planned):
- **Expect the task count to grow.** Each S03 port needed:
  - oracle-first recording of the branches the existing goldens miss (S01 has six seed
    cases);
  - fix-first for the bash defects that recording turns up;
  - a pure merge layer held to the bash, and the bash's output recorded as goldens and
    pushed before the delete (S03-T07's pattern, `tests/golden/agents/`).

  S03 went from 4 tasks to 7. Split early rather than overflow a task.
- **Python resolves paths; the bash used the path `wiki` was started through.** Anything
  seed writes or compares as an absolute path (shell-command configs, button commands, the
  overlay's paths) is checked for a vault reached through a symlink. Compare resolved, and
  state what changes (S03-T06, CHANGELOG 0.7.18 / 0.7.19).
- **`require_cmd jq` in `wiki` is there for seed alone.** It goes with `lib/seed.sh` in this
  slice's last task, and the bootstrap no longer needs jq.
- **Byte parity traps** (KNOWLEDGE, S03-T05): bash's `printf %-Ns` pads by bytes, prompts
  must flush stdout first, and a golden must not hold a machine-dependent number.
