---
milestone: M027
slice: S02
task: T04
project: llm-wiki
closed: 2026-06-10T16:50:00+0200
verification: passed
---

# M027-S02-T04 -- Summary

## Commits

- `bacb1f3` -- feat(M027-S02-T04): wiki index CLI verb + folder_index config knobs
- `769d34f` -- plan(M027-S02-T04): wiki index CLI verb + folder_index config knobs

## Outcome

`wiki index` is live: the dispatcher's `cmd_index()` (help heredoc per
`cmd_dedup` pattern, case-table entry, usage-header lines) shells into
`collectors/folder_index.py main(argv)`. `wiki index` syncs every
`kind=local` `personal.watched_folders` entry, `wiki index <root-id>`
exactly one, `--force` bypasses the delta-skip. `kind=smb` entries are
INFO-skipped (NAS lands in S06; selecting one by id errors with that
hint). Per-root failures are fail-soft (WARNING + continue), exit 1 if
any root failed; nothing configured → friendly hint + exit 0. The three
caps are config knobs now: `limits.folder_index_max_depth=4` /
`folder_index_recent_n=20` / `folder_index_max_tree_entries=500`
(config.py + config.example.yaml + KEY_ADDITIONS migration, same commit).
CONFIG is imported lazily inside `main()` so the walker module stays
importable without config side effects; a `__package__`-guarded sys.path
bootstrap covers direct script execution.

## Deviations from plan

- None — plan held (incl. the predicted round-trip fixture bump 84→87;
  the `migrate_additions_idempotent` fixture needed the 3 keys too).

## Follow-ups

- ⚠️ E2E on lxw outstanding: real `wiki index` against a configured
  watched folder needs `wiki update` + a `personal.watched_folders`
  entry on the operator side. CLI path is unit- + smoke-verified
  (direct execution: `--help` and empty-config no-op both exit 0).
- S03 design note: producer needs the digest in-context — `wiki index`
  is manual-only today; scheduling (piggyback vs system-scheduler) is
  CONTEXT Q6, S06 territory.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_folder_index_collector.py
tests/test_migrate_config_keys.py -q` then `uv run pytest -q` -- passed.
Full suite **1230 passed, 0 failed** (1225 → 1230: 5 CLI tests).
`bash -n wiki` clean.
