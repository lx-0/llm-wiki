---
milestone: M034
slice: S06
task: T06
project: llm-wiki
closed: 2026-10-16T05:47:00+02:00
verification: passed
---

# M034-S06-T06 -- Summary

## Commits

- `1e393be` -- M034-S06-T06: release 0.8.0 — the CHANGELOG's "For your vault" for an
  engine of 0.7.3 or older; docs/cli.md lists every catalogue command (ten were missing; lint
  18 checks, five producers) and tests/test_cli_docs.py keeps it so; the output gate covers
  cli.py, which answers help/auth/refresh-dashboards itself (7 print( → say); `wiki triage`
  and `wiki dream-entity` help name their real verbs and flags (no `done`, no USD
  `--cost-cap`), and the dream-cycle agent spec its real size gate; the DECISIONS milestone
  entry takes the nine exit criteria one by one; backlog: agent-task write scope (the one
  SDK path outside the substrate rule), the architecture diagram's stale panels

## Outcome

Engine **0.8.0** is released. Exit criterion 9's release half is done, and the backlog half
is T07.

- **CHANGELOG 0.8.0** opens with what M034 is: released step by step from 0.7.4 to 0.7.34.
  - **"For your vault":** five steps, once, for an engine of 0.7.3 or older:
    1. `wiki update`;
    2. `wiki seed` plus an Obsidian restart;
    3. overlays recaptured before `--force`;
    4. a stray in-vault `.venv` on a cloud vault, deleted with doctor's line;
    5. one real `wiki compile`, the call S05-T06 could not make.
  - It then says what an operator will notice, what changed, and what 0.8.0 itself fixed.
- **`docs/cli.md`** lists every catalogue command. The ten missing ones got rows: `auth`,
  `backfill`, `bridge`, `dream-entity`, `install-shortcut`, `pin`, `preprocess`, `stats`,
  `take`, `triage`. `tests/test_cli_docs.py` refuses a command without one, and it was RED on
  exactly those ten.
- **The output gate** now covers `cli.py`, which answers `help`, `auth` and
  `refresh-dashboards` itself and prints every banner. Its 7 `print(` calls became `say`,
  byte-identical, and the gate went RED on all 7 first.
- **The DECISIONS milestone entry** takes the nine criteria one by one:
  - 1–7 met (6 as amended);
  - 8 met with its caveat (no real model call under a sandboxed `HOME`);
  - 9 met for the release, with the backlog reconciliation in T07.
- **The diagrams stay.** No box names an M034-moved component (scanned, not assumed).
  Their two stale panels, older than M034, went to the backlog.

## Deviations from plan

- **Defects fixed in passing:**
  - **Help texts.** `wiki triage --help` named a `done` verb the parser does not have (its
    verbs are `list`, `accept`, `dismiss`). `wiki dream-entity --help` offered `--cost-cap`
    and a USD cap dropped on 2026-05-23; its flags are `--max-chars` and `--max-turns`. Both
    were checked against the real parsers. The two `dream-entity` bash goldens re-recorded
    with only those lines changed.
  - **The dream-cycle agent spec** told the agent about the same removed cap. That one
    sentence now names the prompt-size gate.
  - **`cli.md`'s lint row** said "8 checks" with the removed `missing_backlinks`. Its
    producer table lacked `folder_curiosity` and `intents`, and placed takes in
    `knowledge/people/` instead of `knowledge/takes/`. The doc audit had missed the lint row
    because it matched only the spelled-out name; its regexes are sharper now (`missing_backlinks`,
    "8 checks", `cost-cap|max_cost_usd|triage done`).
  - **`test_output_seam.py`'s docstring** said 25 modules; T02 converted 36.
- **The `cli.py` gate gap.** T02 had scoped the gate to the handler modules. Criterion 5
  ("command output goes through core/console") would not have been honest for the commands
  the dispatcher answers itself.
- **The version check.** The plan's "`wiki version` reports 0.8.0" was wrong: `wiki version`
  prints the git revision, tag and origin, and the project is a virtual one in `uv.lock`, not
  an installed package. The version lives in `pyproject.toml` and `uv.lock`; both say 0.8.0.
- **Timestamps corrected.** The T05 plan and summary and the T06 plan had estimated times
  later than the real ones. They are now set from the commit times.

## Follow-ups

- **T07 (milestone close):** the backlog fan-out, the DECISIONS 2026-08-27 method over 86
  open files, then the PRIORITY.md re-cut and `reassess-roadmap`. New items to rank:
  - `agent-task-write-scope.md`. Security-relevant: four agent specs run `acceptEdits` with
    no write scope, on substrate input, outside AGENTS.md's HARD rule.
  - `architecture-diagram-stale-panels.md`.
  - `bare-uv-run-forms-in-docs.md`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_cli_docs.py -q`: RED on the ten commands, then green.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2680 passed, 1 skipped.
- `bash /tmp/ci-gates.sh`: clean.
- `bash /tmp/m034-doc-audit.sh`: 0 hits in 38 files, with the sharper regexes.
- `PYTHONPATH=scripts uv run --frozen python /tmp/m034-docs-current.py`:
  - no catalogue command missing from `cli.md`;
  - all 110 FEATURES script paths exist;
  - engine-layout names every module (brace forms included).
- `pyproject.toml` and `uv.lock` (`llm-wiki`, virtual) both say 0.8.0.
- CI on `1e393be`: both runs green (`ci` 38847155744, `secrets-scan` 38847155748).
