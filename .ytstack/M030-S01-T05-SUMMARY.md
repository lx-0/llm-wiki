---
milestone: M030
slice: S01
task: T05
project: llm-wiki
closed: 2026-08-25T10:00:00Z
verification: passed
---

# M030-S01-T05 -- Summary

## Commits

- `feat(publish): wiki publish --dry-run CLI + catalog row (M030-S01-T05)` (committed with this summary)

## Outcome

`wiki publish` exists in the CommandSpec catalog (group Knowledge ops, handler `publish/cli.py`, rich `H_PUBLISH` help). `build_publish_plan` wires the whole S01 pipeline: manifest → stability-aware `map_slugs` → `description_index` → `build_payloads` → `plan_delta`. `--dry-run` prints the human plan (totals + per-action lines), `--json` emits the stable machine seam `{create, update, retract, unchanged}`. Without `--dry-run` the command prints "live publish is not implemented yet (M030-S02)" and exits 1 — no silent no-op. NOT yet run against the real lxw vault (that is S02-T05's live step); verified at function level on fixture vaults.

## Deviations from plan

None.

## Follow-ups

None — S01 complete, reassess at the slice boundary.

## Verification

Command: `uv run pytest tests/test_publish_cli.py -q` (4 passed) + `uv run pytest -q` (1819 passed, 1 pre-existing skip) -- passed.
