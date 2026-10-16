---
milestone: M034
slice: S06
task: T04
project: llm-wiki
closed: 2026-10-16T05:07:03+02:00
verification: passed
---

# M034-S06-T04 -- Summary

## Commits

- `d05147e` -- M034-S06-T04: one collect verb — `wiki collect <name> -- <flags>` hands
  everything after `--` to the collector module's main(argv) (screenshots / browser / tabs;
  youtube and folder-index keep `ingest-youtube` / `index`, their prog names that verb); the
  three by-path entry scripts are deleted; the output gate covers every collector module
  (24 print( → say); `refresh-dashboards` joins the catalogue as a builtin with help and
  --dry-run; docs/PROCESS.md teaches no bare `uv run --project .wiki` line (11 → 0); 0.7.33

## Outcome

Exit criterion 6 is met: a lazy registry (T03) and one collect verb.

- **The pass-through.** `collectors/cli.py` splits the argv at the first `--`. With a tail,
  it imports the module from `collectors.MODULES` and exits with that module's `main(tail)`.
  - An unknown name gives the existing error.
  - A collector without a `main` is an error that lists the ones that have one. The list is
    computed, not written down.
  - `--list`, a missing name, or the Registry flags (`--dry-run` / `--incremental` /
    `--account`) beside a `--` are usage errors (exit 2).
- **The collectors' own CLIs.** screenshots, browser, tabs and youtube take
  `main(argv: list[str] | None = None)`. Each parser's `prog` names the command that runs it:
  `wiki collect <name> --`, and for youtube `wiki ingest-youtube`. folder-index already did.
  - Their 24 `print(` calls go through `say`.
  - `tests/test_output_seam.py` now covers all 14 collector modules, since `wiki collect` runs
    each of them.
- **The entry scripts.** The three by-path scripts are deleted, and `test_cli_dispatch`'s runpy
  list shrank to the four entry modules that remain.
- **`wiki refresh-dashboards`** is a catalogue `builtin` with help, so `wiki help` lists it.
  - `--dry-run` runs both generators' own `--dry-run` through the child runner. The exit code
    is the first one that fails.
  - A word it does not know is refused (exit 1).
- **Docs.** `docs/PROCESS.md` has 0 bare `uv run --project .wiki` lines (11 before).
  engine-layout, FEATURES, cli.md, AGENTS.md and CHANGELOG 0.7.33 match.

## Deviations from plan

- **youtube's `prog` is `wiki ingest-youtube`, not `wiki collect youtube --`.** Its catalogued
  verb stays (help text, menu entry, a peer of `ingest-html`); the pass-through reaches the
  same `main(argv)`. DECISIONS 2026-10-16 "A collector's own flags go after
  `wiki collect <name> --`" records the choice and the strict reading it rejects.
- **The output gate grew to the collector modules.** Not in the plan, but the pass-through
  makes their `main` command output. Before: 24 `print(` in scan_browser (15), scan_tabs (7)
  and scan_screenshots (2), all converted. RED first: the extended gate listed all 24.
- **Logging for the pass-through runs.** They now log through `collectors/cli.py`'s setup: to
  the terminal and to `logs/collectors.log`. The deleted browser and tabs scripts set up no
  logging at all, so their `log.info` lines went nowhere.
- **Stale facts fixed in passing (pathfinder):**
  - browser and tabs told the operator `Run 'uv run python scripts/compile.py'` after a
    report; they now say `wiki compile`.
  - scan_youtube's docstrings cited calendar's `--year`, a flag that exists nowhere.
  - `ingest_youtube.py`, `index_folders.py` and `test_cli_dispatch`'s guard still gave the
    double-import reason that T03 removed for `collectors`. They now give the real reason:
    run as `-m`, the module would be a second copy beside the registry's.
  - PROCESS.md:
    - the scanner table lacked wispr, pictures, capture and folder-index;
    - "alle zehn" became fourteen;
    - the dashboard sections claimed a 30 s timeout (now the `limits` knob, 300 s), a
      "total cost" callout (now tokens), and bash wrapper helpers that the port removed.
  - FEATURES said "thirteen" collectors, left wispr and capture out of the auto list, and
    taught `uv run python scripts/collectors/scan_<name>.py` (fails since M033).
  - AGENTS.md listed `collectors` as an eagerly importing package and named the deleted
    scripts and a bash `python -m` line that S05 removed.
  - engine-layout's "How a module runs" used the bare form in both examples. Both now use
    `<venv>/bin/python`, with the reason.
  - The dashboard generators' docstrings now name `wiki refresh-dashboards`.

## Follow-ups

- **T05 (README ≤ 300, AGENTS.md ≤ 250, the doc audit), input found here:**
  - README's stat card and both collector lists say eleven, with the old `scan-*` names
    (fourteen today).
  - README's "Running scripts manually" teaches the bare forms, and its "Hooks always use
    Option B" is stale.
  - README's CLI paragraph says bash stays the source of truth for each subcommand (not since
    S05).
- **T06 / backlog:** `backlog/bare-uv-run-forms-in-docs.md` lists where the bare `uv run`
  form is still taught outside PROCESS.md, operator-facing (README, cli.md's one-shot
  scripts) and developer-facing (AGENTS.md, FEATURES, docstrings), with a direction for each.
- **Backlog closed:** `collect-flags-one-verb.md` shipped as proposed.
- **Commit hygiene:** `010763e` carries a `Co-Authored-By` trailer against the
  no-attribution rule. It is pushed, and rewriting it would take a force push, so it stays;
  `d05147e` onwards carry none.

## Verification

Commands:
- `uv run --frozen pytest tests/test_collect_passthrough.py tests/test_cli_dispatch.py
  tests/test_cli.py -q`: RED first. The passthrough test failed 8 times while `collect`
  rejected the tail, then 4 times for the signatures. The `refresh-dashboards` tests failed 4
  times, and the extended output gate listed 24 calls. Then green, 108 passed together with
  the gate and menu tests.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2677 passed, 1 skipped. The four help
  goldens and `oracle/help.txt` were re-recorded. `git diff -w` shows one added line each
  (the new row); the rest is the column widening by two for the 18-character name.
- `bash /tmp/ci-gates.sh`: clean.
- `grep -c "uv run --project .wiki" docs/PROCESS.md`: 0.
- On a scratch vault holding the working tree, through `./.wiki/wiki`
  (`/tmp/m034-scratch-t04.sh`, sandboxed HOME):
  - `collect tabs -- --help` prints `usage: wiki collect tabs -- [-h] [--dry-run]
    [--backup-dir BACKUP_DIR]`.
  - The other own CLIs show their usage lines.
  - `--backup-dir` reaches `main`.
  - The four refusals answer as tested.
  - The Registry run `collect tabs --dry-run` is unchanged.
  - `refresh-dashboards --dry-run` printed both JSON payloads (12 and 4 keys). A file
    snapshot of the vault differed only in `__pycache__` bytecode.
  - `refresh-dashboards` wrote both fragments.
- CI on `d05147e`: both runs green (`ci` 38843883820, `secrets-scan` 38843883815).
