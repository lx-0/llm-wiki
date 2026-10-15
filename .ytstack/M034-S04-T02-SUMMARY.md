---
milestone: M034
slice: S04
task: T02
project: llm-wiki
closed: 2026-10-16T02:30:00+02:00
verification: passed
---

# M034-S04-T02 -- Summary

## Commits

- `e3ebb8c` -- M034-S04-T02: the seed core in Python — walk, overlay apply / compute, derive — held to 27 goldens recorded from the bash; core.jqjson writes JSON the way jq 1.7 does
- `e71c3a7` -- M034-S04-T02: fix first — --extract-custom keeps the settings you turned off (0.7.23); jq's paths(scalars) dropped every false
- `bcd0f09` -- M034-S04-T02: fix first — --extract-custom captures a setting whose type changed (0.7.22); it died in silence with exit 5

The task was planned in `e638ed3`, T01's summary commit. The hook's draft named that commit
as T02's first.

## Outcome

The seed's pure core runs in Python.

**`core/seed.py`:**
- `walk` lists every file `wiki seed` writes, in the bash's order, and how each is seeded:
  copy / overlay / plugin-list / snippet-list / button-templates / shell-commands / env.
- `apply_overlay` merges element-wise, arrays by index, and an overlay `null` keeps the base.
- `compute_overlay` is the leaf diff, and `overrides` gives its count.
- `derive` returns the text written for an overlay-managed config.

**`core/jqjson.py`** reads, compares and writes JSON as jq 1.7 does:
- number literals are kept, read as `Decimal`;
- `render` writes `jq .`, and `canonical` writes `jq -S .`;
- `same` is jq's `==`;
- the leaf, get and set paths follow jq. `agents.render` delegates to it, and S03's agent
  goldens still hold byte for byte.

Python matches 27 goldens recorded from the bash functions, composed as the seed composes
them, and the walk matches the order `seed-check-unseeded` pins. On a copy of lxw's
`.obsidian/`:
- compute equals the bash on all 7 overlay-managed files, quickadd with 73 overrides;
- derive equals the bash on the 3 files with an overlay.

Two silent bash defects were fixed first and released:
- **0.7.22:** `--extract-custom` died with exit 5 when a setting changed type.
- **0.7.23:** it dropped every `false` setting. jq's `paths(scalars)` filters on the value, so
  a later `--force` turned those settings back on.

## Deviations from plan

- **Two fix-firsts, not one.** The `false` leaf bug was found while probing jq's path order
  for the port. It is the more serious of the two: lxw's live `graph.json` overlay lacks
  `showTags` and `hideUnresolved`, both `false` live and `true` in the template.
- **Numbers needed more than json.dumps.** jq 1.7 keeps number literals, so `core.jqjson`
  reads them as `Decimal` and has its own renderer.
- **`_files_equivalent` was not ported.** Its JSON branch was dead, so copied files compare
  byte for byte. AGENTS.md says so now.
- **Two more files changed:** `core/agents.py`, whose render is delegated, and
  `docs/engine-layout.md` / AGENTS.md.
- **No separate walk golden:** the walk is held to an existing oracle golden.

## Follow-ups

- **Operator (0.7.23's "For your vault"):** re-capture the lxw overlays before any `--force`.
  The commands are `wiki seed --extract-custom .obsidian/graph.json` and the same for
  `.obsidian/plugins/extended-graph/data.json`. Otherwise `--force` turns `showTags` /
  `hideUnresolved` back on.
- **Backlog:** `.ytstack/backlog/overlay-cannot-carry-deletions.md`.
  - An overlay cannot carry removals. lxw's `graph.json` has fewer colour groups than the
    template, and `--force` brings them back.
  - Recommended: a round-trip guard after T04, in Python.
- **T03 ports the merges** (`_merge_list_union`, `_merge_registry`, the `.env` append, the
  dashboard rewrite in-process) on `core.jqjson`:
  - jq's `unique` (a sorted union) and array subtraction are still to add to it;
  - the live-copy parity run is the same shape (`/tmp/live-parity.py`, not committed).
- **T05 deletes** the bash-running half of `tests/test_seed_core.py`; the goldens stay.

## Verification

Commands:
- `uv run --frozen pytest tests/test_seed_core.py -q` -- passed (60).
- `uv run --frozen pytest tests/test_bash_oracle.py tests/test_seed.py -q -k seed` -- passed.
- S03's agent and hook tests with the shared renderer -- 116 passed.

Gates: ruff, format and ty are clean. Live parity on a copy of lxw had 0 failures. CI is
green for `bcd0f09`, `e71c3a7` and `e3ebb8c`. Full suite at `e3ebb8c`: 2606 passed,
1 skipped.
