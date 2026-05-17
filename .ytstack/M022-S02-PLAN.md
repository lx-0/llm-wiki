---
milestone: M022
slice: S02
project: llm-wiki
created: 2026-05-17T13:30:37Z
status: planned
task_count: 3
completed_tasks: 0
---

# M022-S02 — Slice Plan

**Goal:** `voice.py` und `pictures.py` archivieren das Source-File nach `raw/inbox-mobile/voice/` bzw. `raw/inbox-mobile/pictures/` statt `<inbox>/.processed/` außerhalb des Vaults. Die derived-artifact-Locations (`raw/voice/<slug>.md`, `raw/notes/pictures/<batch>.md`) bleiben unverändert. Dedup-Logik (Existenz-Check im Archiv) wandert mit auf die neue Vault-Location.

## Tasks

- [ ] T01 — `scripts/collectors/voice.py`: `ARCHIVE_SUBDIR = ".processed"` (line 35) entfernen; neuen Konstant `MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "voice"` einführen; alle Stellen, die `archive = inbox / ARCHIVE_SUBDIR` bauen, auf `MOBILE_ARCHIVE_DIR` umschreiben (inkl. Dedup-Skip in `_list_inbox`-Pendant und Move in line 211 + 249).
- [ ] T02 — `scripts/collectors/pictures.py`: analog. `ARCHIVE_SUBDIR` (line 47) entfernen; `MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "pictures"`; Move-Site (line 429) umschreiben.
- [ ] T03 — Tests in `tests/test_collectors_voice.py` und `tests/test_collectors_pictures.py`: verifizieren dass Original im Vault-Archive landet UND `<inbox>/.processed/` während des Test-Runs nicht angefasst wird (assert nicht-existent).

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Live-Probe-Plan (deferred bis S03 Migration läuft): eine echte iOS-Shortcut-Voice-Note in `<voice_inbox>/` droppen, `wiki collect voice` laufen, Resultat in `raw/inbox-mobile/voice/` UND `raw/voice/<slug>.md` auditen.

## Notes

- Dedup-Mechanik ändert sich semantisch: heute "ist das File schon in `<inbox>/.processed/`?" → neu "ist das File schon in `raw/inbox-mobile/<source>/`?". Funktional identisch, Pfad anders.
- Collectors müssen `MOBILE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)` beim Erststart aufrufen — auf fresh-installed Vaults existiert der Folder noch nicht (Template-Sync erfolgt erst in S03).
