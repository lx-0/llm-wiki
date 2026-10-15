---
milestone: M034
slice: S01
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 6
completed_tasks: 3
---

# M034-S01 -- Slice Plan

**Goal:** Every bash-owned command's observable behaviour is recorded from the bash version
into the oracle, and `wiki` execs the venv's Python straight into the dispatcher (no `uv run`
parent). The thin wrappers (menu, doctor, status, version, dream routing, OAuth aliases) live
in the Python catalogue.

## Tasks

- [x] T01 -- Bash oracle, read-only commands. A fixture vault plus a fixture `HOME`, the
  bash `wiki` run under them, and normalised stdout / stderr / exit code recorded as goldens
  for:
  - `help` and the four bash help texts;
  - `version`, `status`;
  - `menu` with no TTY, `doctor --json`;
  - `config get/keys/path/status`;
  - `hooks status`, `skills status`;
  - `dream` / `dream-entity --help` routing.

  Extends `tests/_oracle.py`, does not fork it.
- [x] T02 -- Bash oracle, mutating commands. The effect on the fixture vault and the fixture
  `HOME` (file tree + contents, with backups named by pattern) of:
  - `config set`;
  - `hooks install/uninstall` per agent and scope;
  - `skills install/uninstall/sync`;
  - `seed` (fresh and `--force`);
  - `install-shortcut`.

  Recorded from bash, committed before any port. `update` gets its own oracle in S05.
- [x] T03 -- Decide open questions 1 and 2 in DECISIONS. One hop = the bootstrap execs the
  venv Python into `cli.py`, and handlers stay `python -m` children. The `llm_wiki` rename is
  dropped. Measure today's process tree for one command (`ps`) as the before number.
- [ ] T04 -- The bootstrap hop. `wiki`'s `_dispatch_python` execs `<venv>/bin/python` with
  `scripts/` on PYTHONPATH (the iCloud `~/.venvs/<vault>-wiki` rule and
  `UV_PROJECT_ENVIRONMENT` kept), and falls back to `uv run` only when the venv is missing
  or `uv.lock` changed since the venv's last sync. That case is today's implicit sync on
  every `uv run`, which must not be lost (DECISIONS 2026-10-15 "One hop").
  Prove it in three ways:
  - the process tree after (dispatcher + handler), measured the T03 way;
  - a test that no `uv` is called while the venv is current;
  - the full oracle, unchanged.
- [ ] T05 -- Port the thin wrappers into `cli_catalog`:
  - `menu`, `doctor`, `status`, `version`;
  - the `dream` / `dream-entity` argv routing;
  - the `gmail-auth` / `gmeet-auth` / `calendar-auth` aliases.

  Their bash functions are deleted; the oracle is unchanged, apart from differences decided
  in the commit.
- [ ] T06 -- Consumers smoke on scratch:
  - the desktop app's `wikiBin` spawn (`menu --json`, `doctor --json`);
  - the eight Obsidian shell-command buttons' command lines;
  - `~/.local/bin/wiki`-style symlink invocation;
  - the use-llm-wiki skill's commands.

  All against the scratch vault at S01's head.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; the oracle covers every
bash-owned command; `wiki` dispatches without a `uv run` parent.

## Notes

The oracle is the contract for S02–S05: each port is measured against what the bash did,
recorded before the port. Normalise only what is genuinely volatile (timestamps, absolute tmp
paths, backup suffixes), and say so in the golden's header.
