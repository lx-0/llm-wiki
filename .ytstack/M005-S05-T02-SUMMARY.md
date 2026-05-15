---
milestone: M005
slice: S05
task: T02
project: llm-wiki
closed: 2026-05-15T20:40:00Z
verification: passed
---

# M005-S05-T02 -- Summary

## Commits so far (auto-tracked)

- `071ef66` — docs(backlog): second-wave substrates — health/calendar/dms/reading/music. **NOT T02 work.** Parallel session committed this while STATE.md had `active_task: T02`.
- `f8e4754` — feat(dashboard): Personal Tasks (Wiki) pane (M005-S05-T01). **NOT T02 work.** T01's closing commit.

(T02 work landed in the commit that closes this task.)

## Outcome

`scripts/dashboard/dashboard_stats.py` gains `_open_action_items_in_entities(knowledge_dir)` — scans `knowledge/people/*.md` + `knowledge/projects/*.md`, locates each file's `## Action Items` section, counts `- [ ]` lines (excludes `- [x]`/`- [X]`), returns `(open_total, entities_with_at_least_one_open)`. Both threaded into `compute_stats()`, both written to `_dashboard-stats.md` frontmatter as `open_commitments` + `entities_with_action_items`.

Callout rendering: when `open_commitments == 0`, prints positive-framing line `📌 **Commitments inbox:** empty — first jamie/gmeet compile will populate this from meeting substrates.` When non-zero, prints paired line `📌 **Open commitments:** N across M entities` (M=1 → "1 entity" singular).

`templates/_dashboard-stats.md` placeholder updated with the new frontmatter keys + the positive-framing inbox-empty line so a fresh vault renders sensibly before the first stats refresh.

Five new test cases in `tests/test_dashboard_open_commitments.py` cover: empty knowledge, single person with 3 open items, mix of `[x]` and `[ ]` (only open counted), entities with no open items don't count, people + projects both counted.

`tests/test_dashboard_stats.py:_base_stats()` extended with the new keys so the existing frontmatter-shape tests keep passing.

Suite: 246 passed (241 + 5 new).

## Deviations from plan

One in-scope amendment: the plan needed `tests/test_dashboard_stats.py` in Files because the new frontmatter keys changed the shape expected by an existing test. Caught by the existing test suite (`test_write_dashboard_stats_frontmatter_shape` + `test_write_dashboard_stats_handles_null_compile_ts` failed because `_base_stats()` was missing the new keys). Plan amended via Bash + fixture extended; both tests re-pass.

## Follow-ups

- T03 creates the cross-entity `inbox-tasks.md` MOC that the dashboard section (from T01) links to.
- T04 verifies templates survive `wiki seed --force`.

## Verification

```
grep -nE "def _open_action_items_in_entities|open_commitments" scripts/dashboard/dashboard_stats.py
# → multiple matches, including the new function

grep -E "^open_commitments:" templates/_dashboard-stats.md
# → open_commitments: 0

uv run --project . python scripts/dashboard/dashboard_stats.py --dry-run | grep "open_commitments\|Commitments inbox"
# → "open_commitments": 0,
# → > 📌 **Commitments inbox:** empty — first jamie/gmeet compile will populate this from meeting substrates.

uv run --project . pytest -q tests/test_dashboard_open_commitments.py
# → 5 passed in 0.04s

uv run --project . pytest -q tests/
# → 246 passed in 0.49s (+5 from prior 241)
```

Result: **passed**.
