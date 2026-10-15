---
milestone: M034
slice: S01
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 7
completed_tasks: 5
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
- [x] T04 -- The bootstrap hop. `wiki`'s `_dispatch_python` execs `<venv>/bin/python` with
  `scripts/` on PYTHONPATH (the iCloud `~/.venvs/<vault>-wiki` rule and
  `UV_PROJECT_ENVIRONMENT` kept), and falls back to `uv run` only when the venv is missing
  or `uv.lock` changed since the venv's last sync. That case is today's implicit sync on
  every `uv run`, which must not be lost (DECISIONS 2026-10-15 "One hop").
  Prove it in three ways:
  - the process tree after (dispatcher + handler), measured the T03 way;
  - a test that no `uv` is called while the venv is current;
  - the full oracle, unchanged.
- [x] T05 -- Port the home & status wrappers into `cli_catalog`: `menu` (home screen,
  `--json`), `doctor`, `version`, and the bare `wiki` entry (home screen on a TTY, help
  otherwise). Their bash functions are deleted; the oracle is unchanged, apart from
  differences decided in the commit.
- [ ] T06 -- Port the argv routing into `cli_catalog`: `dream` / `dream-entity` (the implicit
  sweep, `list-candidates`, `web-research`, their banners) and the `gmail-auth` /
  `gmeet-auth` / `calendar-auth` aliases. Their bash functions and case lines are deleted, and
  the oracle is unchanged.
- [ ] T07 -- Consumers smoke on scratch:
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

**Re-cut after T04 (2026-10-15).** The old T05 split in two, and the consumer smoke became
T07.
- **`status` moved to S03-T02.** `cmd_status` is a banner over two bash libraries:
  `config_cmd_status` (`lib/config.sh`, ported in S02-T02) and `hooks_status_table`
  (`lib/hooks.sh`, ported in S03-T02). Porting it in S01 would either pull both forward or
  call back into bash, and "no bash fallback" is a locked decision.
- **The split is by the catalogue machinery each half needs.** T05 needs the in-process
  bare entry and plain handler commands; T06 needs args-prefixed routes and aliases.
