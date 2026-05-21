---
milestone: M024
slice: S02
status: planned
created: 2026-05-21
---

# M024-S02 — Email-discovery wired into the gmeet run loop + config + migration

`discovery = folder-scan ∪ email-link-scan`. Both producers feed one stub list;
existing skip-by-Drive-file-id prevents double-writes. Windowed scan (no email
watermark) → idempotent via file-id dedup.

## Tasks

- [x] T01 — `_GmeetAccount` + resolver read the `email_discovery` sub-block
  - `scripts/collectors/gmeet.py` `_GmeetAccount`: add `email_discovery_enabled:
    bool`, `email_senders: tuple[str, ...]`, `email_folder: str`,
    `email_backfill_days: int`. `_resolve_gmeet_accounts` reads
    `block.get("email_discovery")` (default: enabled=True, senders=
    ("gemini-notes@google.com",), folder="INBOX", backfill_days=30).
  - Test: resolver picks up the block + defaults.

- [x] T02 — email-discovery producer in `_run_one_account`
  - After folder-scan stubs, if `email_discovery_enabled`: `resolve_reader`
    (from the account body via `CONFIG.personal.accounts[id]`); `scan_deep(folder,
    since=now-backfill_days)`; filter `meta.from_addr` against `email_senders`;
    `extract_drive_doc_ids(body_html or "" + body_text or "")`; for each id not in
    `already_present` → `files.get` metadata stub → append to the stub list.
  - Folder-scan failure (no folder_id / list error) must NOT abort email
    discovery — degrade gracefully, run email part independently. Reader error
    (`MailboxReadError`) / no reader → log + skip email part, keep folder results.
  - No email watermark: windowed re-scan + file-id dedup = idempotent.
  - Test: fake reader + fake Drive client → email-only account ingests; dedup
    against a doc already in `already_present` skips the `files.get`.

- [x] T03 — config field + example + migration
  - `config.example.yaml`: document `gmeet.email_discovery` under the example
    account (enabled/senders/folder/backfill_days + comment).
  - `scripts/migrations/migrate_config_keys.py` `migrate_account_additions`:
    inject `email_discovery` default block into any account with a
    `gmeet` block (kind gmeet-api) lacking it.
  - Test: extend `tests/test_migrate_config_keys.py` — account with gmeet block
    gains email_discovery; idempotent; account without gmeet untouched.

## Verification

`uv run --project .wiki pytest tests/ -q -k "gmeet or migrate or thunderbird"`
