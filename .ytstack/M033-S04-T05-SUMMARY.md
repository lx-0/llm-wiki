---
milestone: M033
slice: S04
task: T05
project: llm-wiki
closed: 2026-10-15T11:55:01+02:00
verification: passed
---

# M033-S04-T05 -- Summary

## Commits

`0d43e13` — the plan + the two characterisation test files (green on the committed
loops). `2621920` — the split. This summary, the slice-plan flip, STATE and the backlog
note follow under the same ref (`git log --grep '^M033-S04-T05'`).

## Outcome

`GmeetCollector._run_one_account` (340 lines → 81) reads as its phase list behind the same
signature: `_discover_docs` (the fetch phase — own-Drive folder resolution + listing, the
gemini-notes email links, the union by Drive id, the notes for the message) →
`_group_by_meeting` (the transform; `_KIND_ORDER` is module-level now) → per group
`_new_stubs_for_group` (skip-existing + same-kind-in-sibling) → `_export_group` (the
dead-letter gate, the export, record / un-park) → `_merge_group` | `_write_group` (the
write phase: the file, the daily rollup line, the sibling registration, the watermark
observation) → `_finish_account` (the watermark / dead-letter commit into the account
state, the parked log line, the message). The per-group accumulators travel on an
`_AccountScan` dataclass; the two verbatim `_Sibling(...)` builds became
`_sibling_from_front`. `CalendarCollector._run_one_account` (195 → 62) mirrors it: auth →
calendars → window → per calendar `_scan_calendar` (`_fetch_events` the fetch,
`_event_block` per event the transform, the etag union + watermark entry) → the account
state + message; the accumulators on `_CalendarScan`, which also carries the loop's
`time_min` reassignment so the move stays pure. The write phase (per-date files, concept
pages) stays in `run()`.

A pure move. Evidence: the string-literal multiset diff HEAD → tree is the new docstrings
plus the dedup of the two `_Sibling` builds (`doc_kinds` / `drive_docs` 6 → 5, `id`
32 → 30) and one re-read of `recurringEventId`; the parity dump (`/tmp/t05-parity.py`, 22
scenarios — gmeet: pair write, three docs in one meeting, legacy merge with one and two
docs, same-kind skip, export failure, parked dead-letter, dry-run on both paths,
incremental, configured `since`, auto-resolved / missing folder, list failure,
email-discovered, auth failure; calendar: three calendars with watermarks on two + `since`
+ a failing calendar + previous etags + a recurring series + cancelled / declined /
holiday / all-day / malformed events + operator prose + a transcript cross-link, a full
run, the include filter, dry-run, auth + list failures) is byte-identical before
(`0f68db8`) and after (`2621920`): 1444 lines of messages, written files, state JSON,
fake-call logs and `collectors.*` log records, zero diff. The gate is green with both
entries removed; the longest function in either module is now `CalendarCollector.run`
at 84 lines.

## Deviations from plan

- The premise was wrong in the measured direction: gmeet's loop had no test at all, so
  the plan's "fixtures from the existing collector tests" became two new characterisation
  files (`tests/test_gmeet_account_scan.py`, 14 cases; `tests/test_calendar_account_scan.py`,
  7 cases), written and green BEFORE the split in their own commit; the calendar cases went
  into a new file instead of `tests/test_calendar_collector.py`.
- No live probe: the scratch vault carries no Google OAuth tokens and the live vault's are
  not copied out; the oracle is the fixture parity dump (slice-plan note).
- The orchestrators landed at 81 / 62 lines, not ~50: the docstrings name the phases and
  the keyword calls wrap one-per-line under the formatter.

## Follow-ups

- `.ytstack/backlog/collector-loop-quirks.md` (indexed in `backlog/PRIORITY.md`, S): the
  calendar `time_min = since` leak into the later calendars of an account (dormant — the
  operator sets no `calendar.since`) and gmeet's merge log counting `len(exports)` after an
  early break — moved verbatim; each is a fix commit with its own test, not this task's.

## Verification

Plan command 1 → the collector suites + harness + gate `116 passed`; `uv run pytest -q` →
**2140 passed, 1 skipped** (2119 + the 21 characterisation cases); `ruff check` → `All
checks passed!`; `ruff format` → the touched files unchanged by explicit path. Plan
command 2 → `0`. Plan command 3 → `diff` empty (`PARITY IDENTICAL`). The gate was seen
RED first with the two entries removed: `340 scripts/collectors/gmeet.py::GmeetCollector.
_run_one_account`, `195 scripts/collectors/calendar_collector.py::CalendarCollector.
_run_one_account`. CI: `0f68db8` green; `0d43e13` + `2621920` recorded in STATE.
