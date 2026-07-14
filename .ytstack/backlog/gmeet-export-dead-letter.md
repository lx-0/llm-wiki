# gmeet collector — negative-cache for un-exportable Drive doc-ids

Status: **backlog** (2026-07-14 triage, finding #11).

## Problem
`collectors/gmeet.py::_discover_via_email` re-scans a 30-day rolling email
window each run (`_DEFAULT_EMAIL_BACKFILL_DAYS=30`) and re-extracts the same
colleague-shared Drive doc-ids. When `files.get` 404s (colleague revoked
access / doc deleted), there is no dead-letter, so the same 4 dead doc-ids are
re-attempted every run (~30 collector-level 404 blocks over a 19-day window:
`1pU1RN`×16, `11-hd6QR6`×7, `1Qx7dq`×6, `1VEPipt06`×4). Retry noise + the
skipped meeting is never surfaced to the operator.

## Fix
Persist a per-account negative-cache in `gmeet-state.json`:
`state[acct.account_id]['export_failed'] = {doc_id: {first_seen, attempts, last_error}}`.
Record the id on the `except GmeetAPIError` export path; skip re-fetch of a
cached-failed id (with a bounded re-probe cadence so a re-granted doc eventually
re-imports). Surface a one-line "N meetings un-exportable (access revoked?)"
summary. Effort M, risk low. File: `scripts/collectors/gmeet.py`.
