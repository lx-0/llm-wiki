---
milestone: M024
slice: S02
status: done
commit: f294e51
---

# M024-S02 — SUMMARY

Email-discovery wired in. `discovery = folder-scan ∪ email-link-scan`.

- **`_run_one_account` restructured** — a folder problem (no id / list error) no
  longer aborts the account; folder-scan + email-discovery are independent
  producers feeding one stub list. Union by Drive file-id; the existing
  two-layer skip-existing prevents double-writes. Only own-folder docs advance
  the folder watermark.
- **`_discover_via_email`** — reuses `resolve_reader(account_body)`, windowed
  `scan_deep(folder, since=now-backfill_days)`, sender allowlist, regex over
  `body_html`+`body_text`, `files.get` stub per new id (skips ids already in
  `already_present` before spending the call). Windowed + file-id dedup =
  idempotent, no email watermark. Reader/permission failures degrade to
  `([], note)` so folder results still ship.
- **Config** — `_GmeetAccount` + resolver read `gmeet.email_discovery`
  (enabled / senders / folder / backfill_days; defaults on, gemini-notes, INBOX,
  30d). Documented in `config.example.yaml`. `migrate_account_additions` injects
  the block into any gmeet-api account (same-commit migration per the hard rule).

Tests: 11 new (2 resolver + 6 producer in `test_gmeet_email_discovery.py`,
3 migration in `test_migrate_config_keys.py`) → 20 M024 tests total, all green.
Pre-existing M014/M016 failures (dream_sampling time-drift + migrate_additions
dream_model) untouched.
