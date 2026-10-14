---
milestone: M033
slice: S04
task: T01
project: llm-wiki
closed: 2026-10-15T01:43:00+02:00
verification: passed
---

# M033-S04-T01 -- Summary

## Commits

`b699dcc` — `tests/test_function_length.py`. Planning commit `5b331f6` (it also carries the
slice-plan re-measurement). This summary, the slice-plan flip and STATE follow under the
same ref (`git log --grep '^M033-S04-T01'`).

## Outcome

Exit criterion 6 is a committed gate. `tests/test_function_length.py` walks every module
under `scripts/` with `ast` (length = `end_lineno - lineno + 1`, decorators excluded,
methods keyed `Class.method`, nested functions included), fails on any function ≥ 150 lines
that is not in `ALLOWLIST`, and fails on any allowlist entry whose function no longer
exists, is under the limit, or grew past its recorded length — the list can only shrink.
`core/config_schema.py` is excluded by path with its reason (the generated-table module,
formatted by hand, read as text by the docs generator). The allowlist carries the live
measurement: **20** functions of 1,402 (the audit of 2026-10-14 said 15 — five were not
counted and four grew since), each with its length; it is S04's burn-down, and every later
task removes the entries it splits. RED was seen on both tests (the empty list listed the 20;
a deliberately stale entry for the 7-line `ellipsize` tripped the shrink rule), then green
with the measured entries; the ad-hoc measurement (`/tmp/fn-length-q.py`) and the allowlist
name the same 20 keys.

## Deviations from plan

- 20 entries, not 15: the five extra functions were assigned to the tasks that own their
  modules in the slice plan (T02 `dream._async_main`; T06 `suggestions/cli.main`,
  `producers/intents.IntentsProducer.run`, `health.render`; T07
  `core/health.check_piggyback_health`), and the task lines now carry the measured lengths.
- The shrink rule also forbids growth (`actual > recorded` is stale), not only "dropped
  below the limit": a listed function that keeps growing would otherwise pass silently.

## Follow-ups

- None. The pyproject comment on the complexity family (`C901` / `PLR09xx` ignored because
  "M033-S04 gates function LENGTH with a committed AST test") now points at a test that
  exists; the complexity thresholds are revisited at the S04 close as that comment says.

## Verification

`uv run pytest tests/test_function_length.py -q` → `2 passed` (after `2 failed` RED);
`uv run pytest -q` → **2119 passed, 1 skipped**; `ruff check` → `All checks passed!`;
`ruff format --check` → clean; the key cross-check → identical. CI: `9606567` green;
`b699dcc` recorded in STATE.
