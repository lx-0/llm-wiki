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
pulled. Upgrading a 0.7.3 vault to the M034 engine is proven on scratch. `lib/common.sh` and
`lib/ui.sh` (whose last caller is update's stash prompt; reassessed after S01) are deleted,
and `wiki` is the ≤ 150-line bootstrap, behind one help system.

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
- [ ] T03 -- One help system. Each port moves its command's help text into `cli_help`:
  `config` / `setup` in S02, `hooks` / `skills` in S03, `update` in T02 (`cmd_help` already
  went in S01-T05). This task checks that no bash help text is left, pins that with a test (no
  `help_*` heredoc in `wiki`), and makes `wiki help` and `wiki <cmd> -h` render from one place.
- [ ] T04 -- `lib/common.sh` and `lib/ui.sh` are deleted, and the iCloud venv rule moves into
  the bootstrap.
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

**What S04 taught for this slice** (reassessment after S04, outcome A: the slice order holds;
these refine the tasks when they are planned):
- **Record first finds defects, every time.** S04's recording turned up seven releases'
  worth, 0.7.20–0.7.26, among them dead dashboard buttons in every vault and settings lost on
  `--force`. Plan T01 for fix-first releases inside it, and read every golden before it is
  committed.
- **Grep the tests for the command name before the switch.**
  - A test that pinned "cli.main refuses a bash-native command" ran seed for real after the
    port, against the checkout's parent.
  - It names `update` now. Once update is ported no bash-native command is left, so that
    test changes to the dispatcher's plain "unknown command" path.
- **Child processes escape in-process guards.** conftest's session guard now fails a run that
  writes next to the checkout. Update's scratch runs pull real engines, so they stay in /tmp.
- **The live shape beats the fixture.** Only a copy of lxw's `.obsidian/` showed the plugin's
  own migrations. For update, the real shapes are a 0.7.3 tree (planned) and a copy of lxw's
  `.wiki/` checkout, taken read-only.
- **The cloud rule's second copy.** When `wiki_venv_dir` moves from `lib/common.sh` into the
  bootstrap (T04), Python still cannot serve it, because the bootstrap needs the venv before
  Python runs. Hold `core/health/engine.py:_CLOUD_PATH_MARKERS` and the bash copy to one table
  of cases.
- **install.sh after S04** seeds through `wiki seed` and needs no jq. Its inline skills
  linking duplicates `wiki skills sync`; T04's install.sh re-check moves it behind the venv
  sync the same way.
- **Push only after the local full run has finished.** `790f93b` was red on main for ten
  minutes.

**What T01 left for T02** (the record: 14 new goldens `tests/golden/bash/update-*.txt`):
- **The refusal test runs `git pull` once update is ported.** In a dev checkout, `cli.main(
  ["update"])` would pull the repository itself. The test changes before the dispatch does.
- **One walker for the hook-environment check.** 0.7.27's bash greps line by line; the port
  calls the walker `wiki doctor`'s `check_hooks_installed` uses, shared, not a third copy.
- **The stash path has a terminal now:** `run_wiki(..., tty=True)` types into a pty, and
  `record_effect(..., tty=True)` records it with the engine's status and stashes.
- **The records hold the steady state.** The config migration's `--apply` is asserted
  (`test_update_applies_the_config_migration`), not recorded. Each new knob would otherwise
  move the records.
