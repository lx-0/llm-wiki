---
milestone: M027
slice: S04
task: T03
project: llm-wiki
closed: 2026-06-10T22:05:00+0200
verification: passed
---

# M027-S04-T03 -- Summary

## Commits

- `7650bd7` -- feat(M027-S04-T03): quarantine states + staleness-gated re-dispatch
- `f4e11f1` -- plan(M027-S04-T03): failure/quarantine states + staleness-gated re-dispatch

## Outcome

Failures now quarantine instead of silently staying pending:
`_mark_failed` (email `_mark_error` template + `failed_as_of_mtime`
staleness anchor + `last_error`/`last_attempt_at`) flips the request to
`stale` (file gone — at resolve time or mid-read), `error` (provider
exception or `.error`), or `not-answered` (sentinel). Batches stop
re-dispatching structurally (`list_pending` selects pending only) and
nothing is ever persisted for a failure. The re-dispatch gate implements
"a later source change invalidates the failure": `done`/`rejected` →
`already_<status>`; `stale` retries only when the file exists again
(`still_missing` otherwise); `error`/`not-answered` retry only when the
file's current mtime differs from the anchor (`unchanged_since_failure`
otherwise — the provider is never even constructed, test-pinned via a
get_provider-raises monkeypatch). Dry-run stays ungated (it is the
preview). Retry paths complete end-to-end: touched file → provider →
persist → `done`.

## Deviations from plan

- Three (not two) T02-era tests rewritten: the missing-file test from the
  T03-skeleton era also moved to the new `stale` semantics (covered by
  the plan's stale row, miscounted in the plan's file notes).

## Follow-ups

- T04 next: e2e on a real local trove — the FIRST LIVE SDK read
  (REGEL #1 boundary for the whole provider path). Needs operator-visible
  cost note (~1 compile_model call on a small file).
- T05 after: informed-consent walk card in `_walk`.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py -q` then
`uv run pytest -q` -- passed. Full suite **1259 passed, 0 failed**
(1256 → 1259).
