---
milestone: M034
slice: S01
task: T04
project: llm-wiki
closed: 2026-10-15T19:35:00+02:00
verification: passed
---

# M034-S01-T04 -- Summary

## Commits

- `cb40e20` -- M034-S01-T04 (fix): the oracle's engine template turns git's automatic maintenance off — a commit starts a detached `git maintenance run --auto`, and on the CI runner (git 2.55) it packed the fresh template's loose objects while a hop test was copying it (shutil.Error: 136 paths under .git/objects 'No such file or directory'; CI on 07f15d1, 2325 passed + 1 error). maintenance.auto=false and gc.auto=0 are set before the first commit, so neither the template nor any copy spawns one; a GIT_TRACE guard watched failing first (the trace showed 'maintenance run --auto --quiet --detach')
- `07f15d1` -- M034-S01-T04: release 0.7.5 — wiki starts its Python commands without a uv run parent (two processes instead of three, 60–75 ms sooner per command; interleaved A/B on the scratch vault, n = 21: the old dispatch line 463 ms median against 367 ms, paired difference 75 ms), with uv run's implicit sync kept behind the .wiki-synced stamp; the seed plugin-order fix (864a09d) gets its note
- `e9eb4a2` -- M034-S01-T04: the bootstrap hop — `wiki` execs the venv's python straight into cli.py, no `uv run` parent per call
- `c977b08` -- M034-S01-T04: the bash oracle records four commands that reach _dispatch_python, from today's bash, before the hop changes how it reaches Python — collect --list (dispatcher + a handler child), an unknown command, the dispatcher's help intercept (links --help), an OAuth alias (gmail-auth); none of the 42 earlier cases went through it. 46 cases
- `4c371e5` -- M034-S01-T04: planned — the bootstrap hop: _dispatch_python execs the venv's python into cli.py (VIRTUAL_ENV + venv bin on PATH, as uv run sets them), uv sync --inexact first only without a venv or with uv.lock / pyproject.toml newer than the venv's .wiki-synced stamp, a relative UV_PROJECT_ENVIRONMENT stays on uv run; four Python-dispatched oracle cases recorded from today's bash first; hop tests with a stub python (pid = exec, argv, env, uv log); the tree after on the scratch vault

## Outcome

`wiki`'s `_dispatch_python` execs `<venv>/bin/python <.wiki>/scripts/cli.py "$@"` directly.
- **The venv** comes from lib/common.sh's one rule: `UV_PROJECT_ENVIRONMENT`, which the
  iCloud rule sets to `~/.venvs/<vault>-wiki`, else `.wiki/.venv`.
- **The environment** gets the two `uv run` variables that have readers: the venv's `bin/`
  first on PATH, and `VIRTUAL_ENV`.
- **The implicit sync is kept.** With no venv yet, or with `uv.lock` / `pyproject.toml`
  newer than `<venv>/.wiki-synced`, `uv sync --quiet --inexact` runs first and the stamp is
  touched. A failed sync stops the command and leaves the stamp alone.
- **A relative `UV_PROJECT_ENVIRONMENT` stays on `exec uv run`,** because uv resolves that
  path itself.

Engine 0.7.5 is pushed.

On the scratch vault with the real uv, after the hop:

```
[70398 <- 70394] <.wiki>/.venv/bin/python <.wiki>/scripts/cli.py collect --list   ← the wiki pid itself, exec'd
  [70412 <- 70398] <.wiki>/.venv/bin/python -m collectors.cli --list             ← the handler
```

Before, the same pid was `uv run …`, with the dispatcher and the handler under it. The
`(bash)` children the poller also lists are command substitutions from the bash phase of the
same pid, before its `exec`. A Python audit hook confirmed that the dispatcher spawns only the
handler, before and after.

Timing, an interleaved A/B with n = 21 on a busy machine:

| Dispatch | Median |
| --- | --- |
| Old line (`exec uv run …`) | 463 ms |
| New line (`exec <venv>/bin/python …`) | 367 ms |
| Paired difference | 75 ms |
| `wiki collect --list` end to end after the hop | 404 ms |

The real sync path was exercised on the scratch vault by pulling `07f15d1`, whose `uv.lock`
changed:
- the first call ran `uv sync` (567 ms) and moved the stamp;
- the second call went direct (412 ms) and left the stamp unchanged.

## Deviations from plan

- **The poller's "most alive at once" is not the right number for this.** It counts the bash
  phase's command-substitution subshells under the same pid. The evidence used is the chain
  of commands (no `uv`, the wiki pid exec'd into python), the audit-hook spawn log, and the
  stub-`$PPID` test.
- **The timing needed an interleaved A/B.** Back-to-back medians drifted by more than the
  effect (234 to 381 ms across series), so old and new dispatch lines were alternated within
  one run.
- **CI found a race in the oracle's own infrastructure (`cb40e20`).** On `07f15d1` one hop
  test errored in setup: 136 paths under the module template's `.git/objects/` vanished
  while `copytree` was copying it. `GIT_TRACE=1` showed the actor: every `git commit`
  starts a detached `git maintenance run --auto`. The runner's git 2.55 packed the ~400
  loose objects, which the local git 2.56 never did. The template build now sets
  `maintenance.auto=false` and `gc.auto=0` before its first commit. A guard (a commit in a
  fresh template under `GIT_TRACE` must start no maintenance) was watched failing first.
  This was latent in T01's session template too.
- **The CHANGELOG [0.7.5] also carries the seed plugin-order fix.** `864a09d` shipped right
  after 0.7.4 without its own note.
- **A cosmetic quirk was noticed and left alone.** `install-shortcut` prints the rc line
  without its quotes (`export PATH=$HOME/.local/bin:$PATH`; shellcheck SC2140). It is
  functionally fine in bash and zsh, because an assignment is not word-split. It stays as
  recorded, and S02-T04's port may change it as a decided difference.

## Follow-ups

- **T05:** route the thin wrappers through the dispatcher. They are `menu`, `doctor`,
  `status`, `version`, the `dream` / `dream-entity` routing and the auth aliases (the aliases
  already go through `_dispatch_python`). After it, `doctor` and `menu` lose their own
  `uv run` (`doctor` today keeps bash as the parent).
- **The other bash `uv run` sites stay until their ports:** `cmd_help`, `_run_script`,
  `_refresh_dashboards`, seed's python helpers and `lib/config.sh`. They are S02–S05's.
- **T06:** the consumer smoke (desktop app, Obsidian buttons, the `~/.local/bin/wiki`
  symlink, the skill) on the scratch vault, at S01's head.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_bootstrap_hop.py tests/test_bash_oracle.py -q`:
  52 passed. Every golden is unchanged, the four dispatched ones included.
- `uv run --frozen pytest -q`: 2326 passed, 1 skipped.
- ruff check and format are clean on the touched tests, and `bash -n wiki` passes.

The guard was seen to fail:
- On the old bash, 5 of the 6 hop tests failed because the uv log showed `run …`.
- The sixth (relative path) passes by design. It failed with its `case` branch removed,
  logging `sync …` instead of `run …`, and the branch was then restored.

CI on `07f15d1` had one error, the git-maintenance race in the template, not the hop; it was
fixed in `cb40e20`. CI is green on `cb40e20` (ci + secrets-scan).
