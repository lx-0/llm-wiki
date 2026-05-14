# Fix: watermark must not advance on a failed scan

**Status:** implementing (2026-05-14).

## The bug

`EmailCollector._run_incremental` / `_run_full` advance the per-account
watermark (`last_run_ts` in `state/email-state.json`) **unconditionally** —
including when the scan never reached the mailbox.

Root cause: a `MailboxReader` signals "scan failed" and "scanned fine, 0 new
messages" **the same way** — it just yields nothing. `scan_metadata` is an
iterator; `ImapReader._connect` returns `None` on connect/login failure and
the scan yields nothing; `GmailReader` logs a warning and `return`s. The
collector can't tell the two apart, so it advances the watermark either way.

Effect: one transient failure on a network-backed reader (gmail-api, imap)
— expired token, wrong password, network blip, rate-limit — moves the
watermark past a window that was never read. The next run starts from the
new watermark and never looks back. Silent, permanent ingest gap, no error.

Seen live: `gmail-personal`'s watermark walked `2026-05-01 → 11:56 → 13:56 →
14:10` across failed login runs; ~2 weeks of mail were skipped until the
watermark was manually reset.

`flush.py` spawns piggybacks with `stdout/stderr = DEVNULL` — so a collector
log line is discarded entirely. "Visible" therefore requires a *persistent*
sink, not just logging.

## The fix

**1. A failure signal — `MailboxReadError`.**
New exception in `adapters/mailbox/base.py`. A reader raises it when it
**cannot complete a scan** of a configured account: missing/invalid
credentials, connect failure, login failure, an aborting HTTP error. It is
*not* raised for "scanned fine, 0 messages" (still an empty iterator) nor for
"no reader at all" (that account never enters the scan loop).

- `ImapReader._connect` raises instead of returning `None`; `scan_metadata` /
  `scan_deep` let it propagate. `list_folders` still catches → `[]` (it is
  informational, not the ingest path).
- `GmailReader.scan_metadata` / `scan_deep` raise on a `_session` error or an
  aborting non-200.
- `ThunderbirdMboxReader.scan_metadata` / `scan_deep` raise when **all**
  configured roots are missing (clear misconfiguration). Per-file open
  errors stay graceful (logged, skipped) — one bad mbox ≠ account failure.

**2. The collector stops advancing the watermark on failure.**
`_run_incremental` / `_run_full` wrap `list(reader.scan_metadata(...))` in
`try/except MailboxReadError` per account. On failure:
- the watermark is **left untouched** — next run retries the same window
  (self-healing);
- `state/email-state.json` records `last_error` + `last_error_at` on that
  account entry (persistent, structured, sits right next to the stuck
  watermark — "stuck + last_error" tells the whole story);
- the error is logged at `ERROR` and collected into `RunResult.errors`.
On a *successful* scan, `last_error` / `last_error_at` are **cleared** — the
state file always reflects current health.

**3. The failure is visible.**
- `RunResult` gains `errors: tuple[str, ...]`.
- `collectors/cli.py` adds a `FileHandler` → `logs/collectors.log` (survives
  the piggyback's DEVNULL'd stderr), prints failures prominently, and
  **exits non-zero** when any account failed.
- `email-state.json` `last_error` is a structured hook a future dashboard
  widget can surface (out of scope here).

## Files

- `adapters/mailbox/base.py` — new `MailboxReadError`.
- `adapters/mailbox/imap.py` — `_connect` raises; docstring contract update.
- `adapters/mailbox/gmail.py` — `scan_metadata` / `scan_deep` raise on
  session error / aborting non-200.
- `adapters/mailbox/thunderbird.py` — raise when all roots missing.
- `collectors/base.py` — `RunResult.errors`.
- `collectors/email_collector.py` — per-account `try/except`, watermark
  guarded, `last_error` recorded/cleared.
- `collectors/cli.py` — log file, error print, non-zero exit.
- Tests: `test_imap_reader.py` (the two "graceful on no-creds / login-fail"
  tests flip to `pytest.raises(MailboxReadError)`), `test_email_collector_*`
  (FakeReader can raise; new "watermark not advanced on failure" test),
  check `test_s02_adapters.py` / `test_s03_gmail.py`.

## Edge cases

- **Multi-account run, one fails:** the failing account is recorded + skipped;
  the others scan + advance normally. The collector never aborts wholesale.
- **`--dry-run`:** still no state writes — a failure is logged + in
  `RunResult.errors` but `email-state.json` is untouched.
- **Account recovers:** next successful scan clears `last_error`.
- **Per-folder failure inside one account (imap):** stays graceful (logged,
  that folder skipped) — only a *whole-account* failure raises. A per-folder
  gap is a known, lesser limitation, not addressed here.
- **`is_configured()` unchanged:** a configured-but-broken account still
  counts as configured; it just raises at scan time instead of yielding
  nothing.
