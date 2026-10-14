---
milestone: M033
slice: S02
task: T03
project: llm-wiki
closed: 2026-10-14T19:36:00+02:00
verification: passed
---

# M033-S02-T03 -- Summary

## Commits

Committed together with this summary under the `M033-S02-T03:` ref — `git log --grep '^M033-S02-T03'`.

## Outcome

`scripts/core/entry.py` is the one place that knows how an engine process starts another:
`module_for("preprocessors/inbox.py") → "preprocessors.inbox"`, `child_env()` (a copy of the
environment with `scripts/` first on PYTHONPATH, an inherited PYTHONPATH kept behind it) and
`python_m(handler, *args)` (the argv). Every engine-to-engine spawn goes through it now:
`cli.py`'s `_run_child` (T02's inline version replaced), the piggyback scheduler (runner and
task both as modules — `python -m core.piggyback_runner <name> <cap> -- python -m lint
--structural-only`), `flush.py`'s compile and dashboard children, and the two
preprocessors' compile trigger. The four bash lines that ran sub-package scripts by file
path (`migrations/migrate_config_keys.py`, `migrations/migrate_log_md_path.py` in `wiki`;
`dashboard/agent_buttons.py` twice in `lib/seed.sh`) spell the same thing as
`PYTHONPATH="$WIKI_DIR/scripts" uv run … python -m <module>`. `grep "sys.executable, str("`
over `scripts/` finds nothing — no engine module is spawned by file path any more, which is
what lets T04 delete the per-module bootstraps. Hooks keep running `scripts/flush.py` by
path (a top-level script gets `scripts/` as `sys.path[0]` from Python itself).

## Deviations from plan

- The dispatcher half of this task had already landed in T02 (the shim deletion forced
  it); T03 moved that logic out of `cli.py` into `core/entry.py` and used it everywhere else.
- `flush.py`'s dashboard helper took a `Path` and logged `script.name`; it takes the
  handler string now (the timeout message names the module path).
- No live piggyback spawn in the dev checkout (it is not a vault); the argv and env are
  pinned by `tests/test_piggybacks.py`, the runner module resolves under `-m`, and the three
  bash-invoked modules were run through the exact `PYTHONPATH=… uv run … python -m` shape.

## Follow-ups

- T04: delete the `sys.path.insert` bootstraps (82 files), rewrite the 28 `scripts.*`
  imports, guard test; `docs/engine-layout.md` gains `core/entry.py` in its tree there (the
  `core/` listing is rewritten for the package-layout change anyway).
- M034 (bash port): `PYTHONPATH="$WIKI_DIR/scripts" … python -m` is the shape the bash
  layer keeps until `wiki` becomes `exec python -m …`.

## Verification

Command: `uv run pytest tests/test_entry.py tests/test_piggybacks.py tests/test_flush_trigger.py
tests/test_cli_dispatch.py -q` → green (RED first: `cannot import name 'entry' from 'core'`;
the piggyback test's new argv assertions failed on the file-path shape); `uv run pytest -q`
→ **2044 passed, 1 skipped**; `ruff check` → `All checks passed!`, `ruff format --check` →
383 files; `grep -rn "sys.executable, str(" scripts` → nothing; `PYTHONPATH=… uv run python
-m migrations.migrate_config_keys --help`, `… migrate_log_md_path --help`, `…
dashboard.agent_buttons shell-commands` → exit 0; `bash -n wiki lib/seed.sh` → ok;
`python scripts/cli.py preprocess --list` dispatches through the helper.
