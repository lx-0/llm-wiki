# Two collector-loop quirks moved verbatim in the T05 split (M034 candidate, surfaced in M033-S04-T05)

**Status:** candidate; two small defects, each its own commit with its own test. Recorded
2026-10-15 (M033-S04-T05). Neither is live for the operator today.

**Today:**

1. `calendar_collector._scan_calendar` reassigns the account's `time_min` to the configured
   `calendar.since` whenever a calendar has no incremental watermark (`elif acct.since:
   scan.time_min = acct.since`) — and the reassignment stays in force for every calendar
   scanned after it in the same account, including the watermarked ones that take the
   `updated_min` path. Pre-split this was a plain local reassigned inside the loop; the split
   carries it on `_CalendarScan.time_min` on purpose so the move stays pure. Effect: with
   `since` set and `incremental` on, a watermarked calendar listed after a non-watermarked one
   is queried from `since` instead of from the backfill window, so recently-updated events
   older than the window are rebuilt into per-date rollups for that calendar only. Dormant:
   the operator's config sets no `calendar.since`.
2. `gmeet._merge_group` logs `[acct] merged N Doc(s) into <file>` with `N = len(exports)`
   even when the per-Doc loop broke early on an unparseable post-merge frontmatter — the log
   line overstates what landed in the rare error branch, and `files_written` still lists the
   file. The parity-pinned characterisation tests (`tests/test_gmeet_account_scan.py`) cover
   the happy merge; the break branch has no test.

**Why it matters:** both are quiet. (1) silently widens a query window per calendar order,
which an operator reading the per-date rollups cannot attribute; (2) misreports in the one
place the operator would look when a merge went wrong.

**Proposal:** (1) resolve the lower bound per calendar — `time_min = acct.since if (not
watermark or not incremental) and acct.since else window_min` — with a recording-fake test
over three calendars (watermarked / plain / watermarked) asserting the third's `time_min` is
the window; (2) count the merged Docs in the loop and log that count, with a test that feeds
a `_merge_into_sibling` result the frontmatter parser rejects on the second Doc.
