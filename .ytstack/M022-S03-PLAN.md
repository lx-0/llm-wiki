---
milestone: M022
slice: S03
project: llm-wiki
created: 2026-05-17T13:30:37Z
status: done
task_count: 4
completed_tasks: 4
---

# M022-S03 — Slice Plan

**Goal:** lxw-State migrieren — alle bestehenden `<voice_inbox>/.processed/*` und `<picture_inbox>/.processed/*` Files in die neuen Vault-Archive-Locations umziehen, danach die jetzt leeren iCloud-`.processed/`-Folder rmdiren. Templates für die neuen Inbox-Zone-Folder ergänzen damit `wiki seed --force` auf fresh installs konsistent ist.

## Tasks

- [x] T01 — `scripts/migrations/migrate_inbox_archive.py` schreiben: liest `CONFIG.personal.voice_inbox` + `CONFIG.personal.picture_inbox`, moved `<voice_inbox>/.processed/*` → `<vault>/raw/inbox-mobile/voice/`, `<picture_inbox>/.processed/*` → `<vault>/raw/inbox-mobile/pictures/`. Conflict-Resolution: Filename-collision → suffix mit `-<mtime-iso>`. Nach Move: `rmdir()` auf die leeren `.processed/`-Folder (try/except OSError für falls noch was drin liegt).
- [~] T02 — ~~Templates~~ **CANCELLED** (`lib/seed.sh` doesn't walk `templates/raw/`; collectors do on-demand mkdir). See T02-PLAN/SUMMARY. `templates/raw/inbox-wiki/.gitkeep`, `templates/raw/inbox-mobile/voice/.gitkeep`, `templates/raw/inbox-mobile/pictures/.gitkeep` anlegen. `wiki seed --force` lokal gegen einen tmp-Vault testen, verifizieren dass die 3 Folder angelegt werden.
- [x] T03 — Migration-Test in `tests/test_migrations.py`: fixture mit fake `<voice_inbox>/.processed/foo.txt` + `<picture_inbox>/.processed/bar.png` → Script läuft → assert Files in Vault-Location, alte Folder weg.
- [x] T04 — Live-Run auf lxw — 47 files migrated, both .processed/ rmdir-ed (2026-05-17T15:44Z) (operator-getriggert via `wiki update` oder direkt `uv run python scripts/migrations/migrate_inbox_archive.py`). Verify: `<voice_inbox>/.processed/` und `<picture_inbox>/.processed/` existieren nicht mehr; `raw/inbox-mobile/voice/` + `raw/inbox-mobile/pictures/` enthalten die migrierten Files. **REGEL #1**: kein "fertig"-Claim bis die Live-Folder-Probe gemacht ist.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Milestone-Closeout: STATE.md flippt `current_milestone: M022` → `last_completed_milestone: M022`, ROADMAP-Slices alle `[x]`.

## Notes

- `migrate_config_keys.py` Aufruf wird in S01 entschieden, wenn `INBOX_ARCHIVE_DIR` etc. als Config-Key landen (heute Plan: keine neuen Config-Keys, alle Pfade hardcoded relativ zu `RAW_DIR`). Falls doch Keys nötig: migration-Eintrag in selbem Commit wie S01-Code, NICHT erst hier.
- Operator-Action für S03-T04: nach Engine-Update einmal manuell triggern. Migration ist idempotent (re-run findet keine Files mehr in `.processed/`), darf bei Bedarf ohne Risiko mehrfach laufen.
