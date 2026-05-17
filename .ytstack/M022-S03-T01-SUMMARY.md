---
milestone: M022
slice: S03
task: T01
project: llm-wiki
closed: 2026-05-17T14:50:00Z
verification: passed
---

# M022-S03-T01 — Summary

## Outcome

`scripts/migrations/migrate_inbox_archive.py` created. One-shot, idempotent migration that moves any pre-M022 `<voice_inbox>/.processed/*` + `<picture_inbox>/.processed/*` into the new vault audit zone (`raw/inbox-mobile/voice/` + `raw/inbox-mobile/pictures/`).

Key invariants:
- Filename collisions → mtime-iso suffix (`<stem>-YYYYMMDDTHHMMSS<ext>`)
- After moves: `legacy.rmdir()` removes the empty `.processed/` subdir (try/except for non-empty edge case)
- Unconfigured `voice_inbox`/`picture_inbox` → skip silently (log "skipped", no crash)
- `--dry-run` previews without writing

## Deviations from plan

None.

## Follow-ups

- Migration not auto-wired into `wiki update`. Operator runs it manually once (T04 plan). Auto-hooking into `wiki update` (alongside `migrate_config_keys.py`) is a future ergonomic improvement; not needed for M022.

## Verification

- Engine-repo dry-run: both sources skipped (unset configs), exit 0.
- Unit test coverage: 6 cases in `tests/test_migrate_inbox_archive.py` (T03).
- Commit: `d776e35`.
