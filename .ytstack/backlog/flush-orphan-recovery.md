# Flush orphan recovery — sweep `sessions/` root, not just `failed-flushes/`

**Priority:** P2 — cosmetic today, but a real gap in the capture→persist chain.

## Problem

The flush state machine (`scripts/core/flush_pipeline.py`) has three terminal
states for a staged file in `.wiki/sessions/`:

- `mark_complete()` — extraction OK, content appended to `daily/`, staged file deleted.
- `archive_failure()` — extraction failed, file moved to `sessions/failed-flushes/`.
- (retry) `pending()` — `retry-failed-flushes.py` piggyback re-processes `failed-flushes/`.

There is a **fourth, unhandled state**: `flush.py` dies *between*
`append_to_daily()` and `mark_complete()` (or before reaching either branch) —
machine sleep, reboot, OOM. The hook spawns `flush.py` detached
(`start_new_session=True`), so a killed process leaves the staged file orphaned
in the `sessions/` **root**.

No consumer recovers it:
- `compile.py` never reads `sessions/` at all.
- `pending()` iterates `FAILED_DIR` (`sessions/failed-flushes/`) only — the
  `sessions/` root is invisible to `retry-failed-flushes.py`.

This contradicts the `flush_pipeline.py` docstring's own invariant
(KNOWLEDGE.md: *"no gap in the chain between capture and persist"*).

## Observed (2026-05-14)

5 orphaned staged files (mtimes 1 May / 4 May), 4 unique session IDs. All 4
session IDs were already present in `daily/` — content *had* been persisted,
only `mark_complete()` never ran (likely pre-`flush_pipeline.py`-refactor
leftovers). Files deleted manually. No data loss this time — but the mechanism
that produced them is still live.

## Fix candidates

1. **`retry-failed-flushes.py` also sweeps `sessions/` root.** A staged file
   directly in `sessions/` older than ~1 h (no live `flush.py` could still own
   it) gets re-fed through `flush.py`. Risk: double-append if the original run
   *did* reach `append_to_daily()` but died before `mark_complete()`. Needs a
   dedup guard — `_is_duplicate()` already keys on `session_id`, so a re-run of
   an already-recorded session would be skipped and the file unlinked. That
   mostly covers it, *if* `_record_flush()` ran. It runs right after
   `append_to_daily()`, so the death window for a true double-append is narrow
   (between `_record_flush()` and `mark_complete()` — those are adjacent).

2. **Make `append_to_daily()` + `mark_complete()` + `_record_flush()`
   crash-consistent.** Reorder so the staged file is renamed to a
   `.processing` / `.done` marker, or move dedup-record + delete into a single
   guarded step. Heavier; (1) is probably enough.

## Decision needed

- Adopt (1) with the `_is_duplicate` guard, or go for (2)?
- Staleness threshold for "this orphan's owner is dead" (1 h? tied to the
  piggyback interval?).
