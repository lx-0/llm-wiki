---
milestone: M034
slice: S05
task: T01
project: llm-wiki
closed: 2026-10-16T03:06:00+02:00
verification: passed
---

# M034-S05-T01 -- Summary

## Commits

- `65ae757` -- M034-S05-T01 (fix): the cloud update records name the interpreter as <PYTHON> — the uv shim links sys.executable into the venv it creates, python3 in a uv venv on macOS and python on the CI runner, so 3166f30 was red on CI
- `3166f30` -- M034-S05-T01: the bash `wiki update` recorded before its port — 14 cases from a fixture engine tracking a local file:// origin (already current, fast-forward, --no-skills, the dirty-tree, diverged and not-a-checkout guards, a cloud-synced vault, the stash path through a pty); the cloud hook warning judged per agent and scope as `wiki doctor` does, instead of one grep that fired with no hook installed (0.7.27)
- `f7cd9fa` -- M034-S05-T01: planned — the bash `wiki update` recorded first (oracle first, fix first)

## Outcome

The bash `wiki update` is on record in 14 new goldens, `tests/golden/bash/update-*.txt`. They
come from fixture vaults whose engine tracks a local `file://` origin:
- already current, a fast-forward, and `--no-skills`;
- the guards: a dirty tree without a terminal, a diverged checkout, not a checkout, an
  unknown flag;
- a vault in iCloud Drive's folder layout: no hooks, hooks from before the move, and current
  hooks;
- the stash path through a pty: re-applied, conflicting (left in the stash), declined, and a
  pull that fails after the stash (restored).

Each record holds the output and the change to the vault and HOME. The stash records also
hold the engine checkout's status and its stashes.

The recording found one defect, fixed in the bash first (0.7.27). In a cloud-synced vault the
update warned that "installed agent hooks still run the engine from the in-vault environment"
even with no hook installed: one grep over four configs decided. It now judges each agent's
wiki hooks in both scopes, as `wiki doctor` does, and names them, e.g. `claude (user)`. A
not-a-checkout engine is now named by its real path; the message used to say `wiki/`.

## Deviations from plan

- **No `tests/test_update_tty.py`.** The pty runner, `run_wiki(tty=True)`, sits in `_oracle.py`
  next to the other runner. The stash cases are recorded by the same `record_effect`, plus an
  engine-state section.
- **Two stash cases beyond the plan:** declined (`n`), and a pull that fails after the stash.
- **The cloud case became three.** A parametrized test also asserts the warning rule directly,
  watched failing on the unfixed bash first.
- **The config migration's `--apply` is asserted, not recorded**
  (`test_update_applies_the_config_migration`). With the fixture's one-key config, the migration
  wrote all 120 keys into the records, which would then move with every new knob. The
  preparation now migrates first.
- **Revisions are named** as `<REV>`, `<NEW-REV>` and `<BASE-REV>`. The diverged fetch line
  carried the shared base, which the regex wrote as `<REV>`. git's own diverging advice is
  switched off in the fixture, because its wording changes between git versions.
- **docs/cli.md's update row was wrong** ("never touches `config.yaml`"). It is fixed in the
  same commit.

## Follow-ups

- **T02 (update in Python):** see the notes in `M034-S05-PLAN.md`, "What T01 left for T02".
  - `test_cli.py`'s refusal test names `update`. Once update is ported it would `git pull` the
    dev checkout, so it changes first.
  - The hook-environment check shares the walker that `check_hooks_installed` uses.
  - Phase 2 must accept the 0.7.3 bash's `--post-pull <rev> [--no-skills]`.
- **Backlog:** `update-hooks-hint-only-when-stale.md`. The "re-run wiki hooks install" hint
  prints after every update that moved the engine. Changing that changes what the hint means,
  so it is not part of the port.
- **KNOWLEDGE:** "Recording `wiki update`: the steady state goes into the record, the
  transition into an assertion".
- **Operator:** run `! /tmp/cleanup-stray-seed.sh`. 0.7.20's `wiki seed` + Obsidian restart and
  0.7.23's re-capture before any `--force` still stand.

## Verification

Commands:
- `uv run --frozen pytest tests/test_bash_oracle.py -q -k update`: passed. That is the 14
  records, the warning rule (4 cases) and the config migration.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2638 passed, 1 skipped.
- After the version bump, `tests/test_bootstrap_hop.py tests/test_dependency_integrity.py
  tests/test_bash_oracle.py tests/test_cli.py`: 194 passed.
- CI on `3166f30`: **red**, 3 failed. The three cloud records carried the uv shim's link to
  `sys.executable`: `python3` locally, `python` on the runner. The interpreter is a
  placeholder now, `<PYTHON>` (KNOWLEDGE lesson 5).
- CI on `65ae757`: both runs green.
