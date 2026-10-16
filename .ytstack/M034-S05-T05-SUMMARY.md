---
milestone: M034
slice: S05
task: T05
project: llm-wiki
closed: 2026-10-16T04:15:00+02:00
verification: passed
---

# M034-S05-T05 -- Summary

## Commits

- `a6f65d9` -- M034-S05-T05: the last bash library folds into the bootstrap — lib/common.sh's cloud rule, shell_quote, sync hint and error output live in `wiki` (129 lines, nothing sourced, `lib/` gone, a budget test); the rule's two copies (bootstrap, doctor) held to one table of cases; install.sh lets the first `wiki` call create the environment and stamp it, and links skills via `wiki skills sync` (0.7.31)

The task was planned in `58a12b1`, T04's summary commit.

## Outcome

The bash is one file. `wiki` is 129 lines and sources nothing, and `lib/` is gone. It holds
only what has to run before Python:
- its own path;
- the cloud rule, which exports `UV_PROJECT_ENVIRONMENT` for a vault in iCloud Drive or
  CloudStorage;
- `die` and the uv check;
- `shell_quote` / `sync_hint` for the failed-sync hint;
- the vault guard;
- the one hop.

`tests/test_bash_budget.py` pins ≤ 150 lines, no `lib/` and no `source`.

**The cloud rule's two copies** — the bootstrap's, and `core.health.engine._in_cloud_path`
for `wiki doctor` — are held to one table of five paths in `test_engine_env_location.py`.
The bash side runs the real `wiki` in a fixture vault per case and reads where the venv was
created.

**`install.sh` no longer builds an environment.** `wiki seed`, the first `wiki` call, has
the bootstrap create it where the rule says and stamp it, and `wiki skills sync` links the
skills. That closes S02's stamp item: the installer's own sync left no stamp, so the first
command synced again. On scratch, with the real installer and real uv, one sync happened
during the install and none on the next command, for a plain vault and for an iCloud vault
(environment at `~/.venvs/lxw-wiki`, nothing in the vault).

## Deviations from plan

- **The installer change was a must, not cleanup.** With `lib/` gone, its
  `source lib/common.sh` would have failed silently. It would then have synced
  `.wiki/.venv` inside an iCloud vault, the very environment the rule keeps out.
  `test_an_install_into_a_cloud_vault_keeps_the_environment_outside_it` catches that, and
  was watched failing against the old installer (a one-off run in /tmp).
- **`die` colours on stderr's terminal state** (`-t 2`). The bash `err` looked at stdout.
  Piped output is unchanged, and core/console's `fail` already does it this way.

## Follow-ups

- **T06: the operator path end to end** (planned): the update from 0.7.3, the desktop's
  spawns, the Obsidian buttons, the shortcut, setup on a fresh vault, one compile.
- **Exit criterion 1 is met:** `wiki` ≤ 150 lines and `lib/*.sh` gone.

## Verification

Commands:
- `uv run --frozen pytest tests/test_bash_budget.py tests/test_engine_env_location.py tests/test_bootstrap_hop.py tests/test_install.py tests/test_bash_oracle.py -q`:
  green.
  - The budget test was RED while `lib/` existed.
  - The env-location cases passed against the old layout first.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2656 passed, 1 skipped. ruff and
  `ty check scripts/core`: clean.
- Scratch:
  - `/tmp/m034-scratch-install-t05.sh`: two installs, one sync each, none after.
  - `/tmp/m034-scratch-update.sh`: 0.7.3 → `a6f65d9`, its bash handing over to the
    lib-less bootstrap and the Python phase 2.
- CI on `a6f65d9`: both runs green.
