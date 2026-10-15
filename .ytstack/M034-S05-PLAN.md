---
milestone: M034
slice: S05
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 5
completed_tasks: 0
---

# M034-S05 -- Slice Plan

**Goal:** `wiki update` runs in Python with the post-pull re-exec of the engine it just
pulled. Upgrading a 0.7.3 vault to the M034 engine is proven on scratch. `lib/common.sh` is
deleted and `wiki` is the ≤ 150-line bootstrap, behind one help system.

## Tasks

- [ ] T01 -- Update oracle, recorded from the bash on a scratch clone with a `file://`
  remote. It covers:
  - the fast-forward pull and the dirty-tree guard (refuse without a TTY; stash, then
    re-apply on confirm);
  - `uv sync`, the migrations and the skills sync (`--no-skills`);
  - the `--post-pull` re-exec and the summary line.
- [ ] T02 -- `update` in Python. Phase 1 pulls; phase 2 re-executes the pulled engine's
  entry with `--post-pull <rev>`, so a changed update procedure applies in the same run.
  Proven at oracle parity. A bash 0.7.3 `wiki update` pulling the new engine must also land
  in the Python phase 2.
- [ ] T03 -- One help system: the bash help texts (`help_config` / `hooks` / `setup` /
  `skills`, `update --help`) move into `cli_help`; `cmd_help` is gone; `wiki help` and
  `wiki <cmd> -h` render from one place.
- [ ] T04 -- `lib/common.sh` is deleted and the iCloud venv rule moves into the bootstrap.
  `wiki` is ≤ 150 lines, and a test pins the bash budget (`wiki` line count; no `lib/*.sh`).
  `install.sh` is re-checked against the new layout.
- [ ] T05 -- Operator path, end to end on a scratch vault at 0.7.3:
  - `wiki update` to the S05 head;
  - then the desktop's spawn path, the Obsidian buttons, the shortcut symlink, `wiki setup`
    on a fresh vault, and one compile;
  - the scratch-vault findings recorded.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; exit criteria 1, 2 and 8 are
met.

## Notes

`update` is the one command that has to work across two engine versions in one run. Port it
last, and prove the cross-version path from the real 0.7.3 tree, not from a fixture.
