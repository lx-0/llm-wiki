---
milestone: M033
slice: S02
task: T02
project: llm-wiki
closed: 2026-10-14T23:55:00+02:00
verification: passed
---

# M033-S02-T02 -- Summary

## Commits

Committed together with this summary under the `M033-S02-T02:` ref — `git log --grep '^M033-S02-T02'`.

## Outcome

No hyphenated module names remain under `scripts/`. `review_wiki.py`,
`optimize_claude_md.py` and `retry_failed_flushes.py` are the renamed modules
(`git mv`, usage docstrings updated); `process_inbox.py` and `ingest_html.py` are
three-line entry modules for `wiki process-inbox` / `wiki ingest-html` whose logic lives in
`preprocessors/inbox.py` and `preprocessors/html_ingest.py`. `cli.py` spawns every handler as
`python -m <module>` with `scripts/` first on the child's PYTHONPATH and the caller's cwd
inherited (`module_for()` maps `preprocessors/inbox.py` → `preprocessors.inbox`;
`tests/test_cli_dispatch.py`, 9 tests). The piggyback table, the one bash info string, the
config-schema comments (→ `docs/config.md` regenerated), the vault template
`AGENTS.example.md`, and every doc that named the old files (AGENTS, README, SECURITY,
FEATURES, PROCESS, engine-layout, cli.md, FEATURES) follow. CLI command names, piggyback
names, config keys, state keys and the desktop's action ids are untouched. `git grep` for
the five old filenames finds only CHANGELOG / `.ytstack` history and the diagram labels
deferred to S05-T05.

## Deviations from plan

- **T03's dispatcher change was pulled forward.** Deleting the two shims left
  `wiki process-inbox` / `wiki ingest-html` pointing at package modules that have no
  `sys.path` bootstrap of their own — by file path they fail on `import core`. The
  `python -m` spawn (`_run_child`) was the planned T03 fix and is the only correct one, so
  it landed here, TDD-first (RED: `cli.module_for` missing; GREEN: 35 dispatch/cli tests).
  cwd is inherited rather than set to `scripts/`, because `wiki ingest-html ./page.html`
  resolves its argument against the operator's directory.
- **The shims came back as entry modules, importable this time.** `python -m
  preprocessors.html_ingest` runs the module twice — `preprocessors/__init__.py` imports it
  for registration, then runpy executes it as `__main__` — and Python warns on stderr on
  every run. A top-level entry module outside the package executes once; the guard test
  spawns both entry modules and asserts no `RuntimeWarning`, and the package module was
  seen producing it.
- Found while verifying: `wiki ingest-html --help` advertised a `--dry-run` flag the
  module never had (argparse: "unrecognized arguments"). Help text corrected in this task.
- `templates/AGENTS.example.md` names `wiki process-inbox` now instead of the deleted
  file — a seeded template, so operators see one template-drift notice on their next
  `wiki doctor` / `wiki seed`.

## Follow-ups

- T03 keeps its remaining scope: `core/piggybacks.py` cmd shapes and
  `core/piggyback_runner.py` spawn onto `-m`; the bash `_run_script` paths unchanged.
- T04 removes the 82 bootstraps now that the dispatcher provides the path; `tests/`
  bootstraps go with it.
- S05-T05: `docs/architecture.excalidraw` labels `review-wiki.py`, `process-inbox.py`,
  `ingest-html.py` (one diagram pass with the three render gates).

## Verification

Command: `uv run pytest -q` → **2039 passed, 1 skipped** (2030 + 9 dispatch tests);
`ruff check` → `All checks passed!`; `ruff format --check` → 381 files formatted; `--help`
of `review_wiki.py`, `retry_failed_flushes.py`, `optimize_claude_md.py` by path and of
`process_inbox` / `ingest_html` via `-m` exit 0; through the dispatcher: `wiki preprocess
--list`, `wiki collect --list`, `wiki review-wiki --dry-run` run (sub-package, sub-package,
renamed top-level); the leftover grep prints nothing. Guard seen failing: `python -m
preprocessors.html_ingest --help` emits "found in sys.modules" (1 line), `python -m
ingest_html --help` emits none.
