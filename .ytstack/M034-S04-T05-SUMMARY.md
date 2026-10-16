---
milestone: M034
slice: S04
task: T05
project: llm-wiki
closed: 2026-10-16T02:37:17+02:00
verification: passed
---

# M034-S04-T05 -- Summary

## Commits

- `a414f91` -- M034-S04-T05: the installer seeds through `wiki seed` after its venv sync, and the bash seed is gone — lib/seed.sh deleted, jq no longer needed anywhere (0.7.26)

The task was planned in `375f034`, T04's summary commit.

## Outcome

`install.sh` seeds the vault with `./.wiki/wiki seed [--force]` after its `uv sync`.
- It first creates `<vault>/.obsidian`; the bash seed used to create it silently.
- jq is gone from its prerequisites.
- A failed seed warns with the command to rerun instead of aborting.

`lib/seed.sh` is deleted. The bash layer is `wiki` (312) + `common.sh` (94) + `ui.sh` (21),
and only `update` is left in bash. The bash-recording halves of the seed core and merge
tests went; their 49 goldens stay and hold the Python. `dashboard.agent_buttons` lost its
CLI, since nothing calls it any more.

On the way, the new installer test found a real defect. `[[ -r /dev/tty ]]` checked the
permission only, so a headless install over an existing vault aborted with "Device not
configured". It is fixed in 0.7.26.

## Deviations from plan

- **The `/dev/tty` fix was not planned.** `tests/test_install.py` found it on its first red
  run.
- **The `agent_buttons` CLI was removed too.** A repo-wide consumer grep found no caller after
  the seed went in-process, and this repo phases nothing out over several releases.
- **Two backlog items** got a pointer from `lib/seed.sh` to the Python. Their content stays
  valid.

## Follow-ups

- **S04 is complete; reassess the roadmap next.**
- **S05 (update + the last bash):**
  - `wiki update` to Python;
  - `wiki` ≤ 150 lines;
  - install.sh's version stamp;
  - install.sh's inline skills linking, which duplicates `wiki skills sync`;
  - `core/health/engine.py:_CLOUD_PATH_MARKERS`, a second copy of the cloud rule.
- **Operator:** `! /tmp/cleanup-stray-seed.sh`, plus 0.7.20's seed + restart and 0.7.23's
  re-capture before any `--force`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_install.py tests/test_seed_core.py tests/test_seed_merges.py -q` -- passed (61).
- `uv run --frozen pytest -q` -- 2619 passed, 1 skipped.

Scratch run: the real `install.sh` with real uv, a sandbox HOME and a decoy jq, on engine
`a414f91`.
- A bare directory became a seeded vault, and `seed --check` showed nothing but up-to-date.
- A second headless install kept the operator's `AGENTS.md`.
- jq was never called.
