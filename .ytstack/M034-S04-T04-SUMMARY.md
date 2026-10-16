---
milestone: M034
slice: S04
task: T04
project: llm-wiki
closed: 2026-10-16T02:31:09+02:00
verification: passed
---

# M034-S04-T04 -- Summary

## Commits

- `d6f1401` -- M034-S04-T04: the oracle's named revision tolerates a case without a checkout — version-not-a-checkout red on main since 790f93b
- `790f93b` -- M034-S04-T04: `wiki seed` runs in Python (0.7.25) — every bash seed golden passes unchanged; `wiki` no longer sources lib/seed.sh nor needs jq
- `4b6e9f8` -- M034-S04-T04: record first + fix first — the bash seed's argv and --extract-custom's refusals recorded; --extract-custom names the right cause for a file without an overlay (0.7.24)

The task was planned in `5c4ae19`, T03's summary commit.

## Outcome

`wiki seed` runs in Python, `scripts/seed_cli.py` on `core/seed`. It covers:
- the argv, with help anywhere and the bash's refusals;
- the banner and mode line;
- a status line per file in the bash's own words;
- the targeted path, where a miss exits 1 with the list of seedable paths;
- `--extract-custom`;
- the dashboard's agent-button region, in-process;
- the dashboards refresh, after a writing run only.

All 29 seed oracle cases passed against the port on the first run. `wiki` no longer sources
`lib/seed.sh` and no longer needs jq; it is down to 312 lines and only `update` is left in
bash. `core.jqjson.setpath` now refuses what jq refuses. The command refuses a directory
without `.obsidian/`.

On the way:
- **0.7.24** made `--extract-custom` name the right cause for a file without an overlay.
- **Two oracle fixes:**
  - the engine copy's commit is named outright as `<REV>`, because an all-letter short hash
    escaped the digit rule;
  - large files are pinned by hash (that was T01).
- **Live-copy run:** the Python seed on a copy of lxw's `.obsidian/`, `dashboard.md` and
  `.wiki/custom/` did what T01–T03 predicted.
- **Scratch run** with the real `wiki` in a brand-new vault: every mode works, and an
  overlay captured with `showTags: false` survives `--force`.

## Deviations from plan

- **The record-first cases changed shape.**
  - The planned "extract on a list" case ran clean on an unchanged seed, because the file
    still equals its template.
  - That exposed the wrong-cause defect, fixed in the bash first (0.7.24).
  - The jq-refusal path is now recorded on an overlay-managed config that became a list.
- **Incident:**
  - `test_cli`'s bash-native refusal test called `cli.main(["seed"])`. After the switch it ran
    the real seed as a child process against the checkout's parent, `projects/lx-0/`, and wrote
    31 vault files there.
  - Fixed at the root, in three places:
    - the test names `update`;
    - `seed_cli` refuses a non-vault;
    - a session guard in conftest fails the run if anything next to the checkout changes.
  - The deletion of the stray files was blocked as irreversible.
    `/tmp/cleanup-stray-seed.sh` is waiting for the operator; it deletes only files whose
    creation time matches that run.
- **Kept as the bash wrote them:**
  - an empty plugin-list file is now reported instead of being called up to date (said in
    the CHANGELOG);
  - the doubled parentheses in "(up-to-date (overlay applied))".
- **Not ported:** the bash created an empty `.obsidian/snippets/` on targeted runs. Python
  creates parent directories only when it writes a file. No golden sees directories.
- **`main` was red for about ten minutes.**
  - `790f93b` was pushed while its full local run was still going.
  - That run, and CI, failed on `version-not-a-checkout`: the named-revision fix ran
    `git rev-parse` in a case whose preparation removes the checkout.
  - `d6f1401` fixed it. Pushing optimistically means watching the local run to its end
    before the next step; this time the failure showed up there first, and the fix followed
    at once.

## Follow-ups

- **T05:**
  - `install.sh` must `mkdir -p <vault>/.obsidian` before `wiki seed`, because the vault guard
    needs it. The bash seed created it silently.
  - It seeds after `uv sync`, `--force` on the overwrite choice.
  - jq leaves the prerequisites; `lib/seed.sh` and the bash halves of `test_seed_core.py` and
    `test_seed_merges.py` go.
- **Operator:** `! /tmp/cleanup-stray-seed.sh` removes the stray vault files from `lx-0/`.
- **Backlog, unchanged:** `overlay-cannot-carry-deletions.md` and
  `dashboard-agent-buttons-callout.md`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_bash_oracle.py tests/test_seed.py tests/test_seed_preserves_caches.py tests/test_cli.py -q -k "seed or bash_native"` -- passed.
- `uv run --frozen pytest -q` at `d6f1401` -- 2666 passed, 1 skipped.

Gates: ruff, format and ty are clean. CI was red on `790f93b` (the case above) and is green
on `d6f1401`. The scratch run in a fresh vault and the live-copy run are as described above.
