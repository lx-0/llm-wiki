---
milestone: M034
slice: S05
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 6
completed_tasks: 6
---

# M034-S05 -- Slice Plan

**Goal:** `wiki update` runs in Python with the post-pull re-exec of the engine it just
pulled. Upgrading a 0.7.3 vault to the M034 engine is proven on scratch. `lib/common.sh` and
`lib/ui.sh` (whose last caller is update's stash prompt; reassessed after S01) are deleted,
and `wiki` is the ≤ 150-line bootstrap, behind one help system.

## Tasks

- [x] T01 -- Update oracle, recorded from the bash on a scratch clone with a `file://`
  remote. It covers:
  - the fast-forward pull and the dirty-tree guard (refuse without a TTY; stash, then
    re-apply on confirm);
  - `uv sync`, the migrations and the skills sync (`--no-skills`);
  - the `--post-pull` re-exec and the summary line.
- [x] T02 -- `update`'s phase 2 in Python: `wiki update --post-pull <rev> [--no-skills]`,
  the steps after the pull (summary line, `uv sync`, the cloud-vault hints, both migrations,
  the skills sync). The bash phase 1 re-executes into it, which is the cross-version path
  every operator takes: a 0.7.3 bash pulling the new engine lands here. The hook-environment
  check shares `wiki doctor`'s walker. Proven at oracle parity, and from the real 0.7.3 tree
  on scratch. (Split from T02 at planning time: phase 1 and phase 2 together touched about
  ten files.)
- [x] T03 -- `update`'s phase 1 in Python: the flags, the not-a-checkout and dirty-tree
  guards, the stash on a terminal, the `--ff-only` pull, the re-apply check, and the
  re-execution of the pulled engine's entry. The bash `cmd_update` is deleted, and with it
  `lib/ui.sh`, whose last caller was the stash prompt. The in-process refusal test (T02's,
  in `test_wiki_update.py`) goes first, and `--help` switches to the `H_UPDATE` that T02
  already moved into `cli_help`. Proven at oracle parity.
- [x] T04 -- One help system. Each port moves its command's help text into `cli_help`:
  `config` / `setup` in S02, `hooks` / `skills` in S03, `update` in T03 (`cmd_help` already
  went in S01-T05). This task checks that no bash help text is left, pins that with a test (no
  `help_*` heredoc in `wiki`), and makes `wiki help` and `wiki <cmd> -h` render from one place.
- [x] T05 -- `lib/common.sh` is deleted (`lib/ui.sh` went in T03), and the iCloud venv rule
  moves into the bootstrap.
  `wiki` is ≤ 150 lines, and a test pins the bash budget (`wiki` line count; no `lib/*.sh`).
  `install.sh` is re-checked against the new layout.
- [x] T06 -- Operator path, end to end on a scratch vault at 0.7.3:
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
  bootstrap (T05), Python still cannot serve it, because the bootstrap needs the venv before
  Python runs. Hold `core/health/engine.py:_CLOUD_PATH_MARKERS` and the bash copy to one table
  of cases.
- **install.sh after S04** seeds through `wiki seed` and needs no jq. Its inline skills
  linking duplicates `wiki skills sync`; T05's install.sh re-check moves it behind the venv
  sync the same way.
- **Push only after the local full run has finished.** `790f93b` was red on main for ten
  minutes.

**What T01 left for the port (T02, T03)** (the record: 14 new goldens
`tests/golden/bash/update-*.txt`):
- **T03: the refusal test would run `git pull` once phase 1 is ported.** In a dev checkout,
  `cli.main(["update"])` would pull the repository itself. The test goes before the dispatch
  changes. T02 must not make plain `update` reachable through `cli.main` either.
- **T02: one walker for the hook-environment check.** 0.7.27's bash greps line by line; the
  port calls the walker `wiki doctor`'s `check_hooks_installed` uses, shared, not a third
  copy.
- **The stash path has a terminal now:** `run_wiki(..., tty=True)` types into a pty, and
  `record_effect(..., tty=True)` records it with the engine's status and stashes.
- **The records hold the steady state.** The config migration's `--apply` is asserted
  (`test_update_applies_the_config_migration`), not recorded. Each new knob would otherwise
  move the records.
