---
milestone: M034
slice: S03
task: T06
project: llm-wiki
closed: 2026-10-16T00:15:00+02:00
verification: passed
---

# M034-S03-T06 -- Summary

## Commits

- `2f5a7ea` -- M034-S03-T06: wiki skills in Python — skills_cli.py at parity with the bash oracle, update's skills step through the entry; a vault reached through a symlink is itself (release 0.7.19)
- `9c56dbc` -- M034-S03-T06: planned + oracle first — six bash skills cases recorded before the port's first line

## Outcome

`wiki skills install [--global|--no-global] / uninstall [--global] / sync / status` runs in
Python (`scripts/skills_cli.py`, engine 0.7.19). It covers:
- the engine-owned check;
- local install, prune and uninstall;
- the global install with the vault registry;
- the `skills.global_install` flag, read fresh and written silently through core.config's
  validated `set` path;
- the status table.

`wiki update`'s post-pull step runs `wiki skills sync` through the entry; a failure there
warns instead of failing an update that is already done. `wiki` no longer sources
`lib/skills.sh` / `lib/config.sh` and is at 412 lines.

All eleven flow goldens pass byte-identical: the five from S01 and the six recorded first.

## Deviations from plan

- **"This vault" is compared on resolved paths**, a decided difference with its own test.
  The bash compared text through the path `wiki` was started on. Python's paths are
  resolved, so for a vault reached through a symlink the port would otherwise have:
  - called the vault's own global link another vault's;
  - left that link behind on `uninstall --global`;
  - doubled the registry line.

  The scratch run hit exactly this: `/tmp` → `/private/tmp`.
- **The same split affects 0.7.18's hook commands.** For a symlinked vault they name the
  real path on the next install: harmless, but 0.7.18's "byte for byte as before" claimed
  too much. That CHANGELOG entry now says so.
- **`skills-help` is static** (`<vault>`), a decided difference.
- **`menu.py`'s `config` hint said `lib/config.sh`.** Fixed.

## Follow-ups

- **S03-T07:** delete lib/agents.sh, hooks.sh, skills.sh, config.sh and the dead helpers
  (`ui.sh`'s `select_*`, `common.sh`'s `backup_file`). The bash-parity tests move to
  recorded expectations.
- **S05:** `install.sh` links skills inline, a second implementation of `skills install`
  (it runs before the engine has a venv). Decide when install.sh is reworked.
- **A stale `.git/index.lock` appeared** 5 s after `9c56dbc`'s commit and push. Nothing held
  it, and the ytstack post-commit hook's T06 draft was missing (the draft that came later
  names `2f5a7ea` as the task's first commit). The hook was most likely killed mid-git. It
  was removed after `lsof` showed no holder. To report to ytstack, not to fix here.

## Verification

Command: `uv run --frozen pytest tests/test_bash_oracle.py tests/test_skills_cli.py
tests/test_wiki_update.py -q` — passed. Full suite: 2520 passed, 1 skipped.

Scratch run on the fresh vault with a sandboxed HOME: status → install → install `--global`
→ status ("linked → this vault", registry ✓) → uninstall `--global` (registry and global
link gone). The update's post-pull skills step relinked the skill through the entry. CI
green on `2f5a7ea`.
