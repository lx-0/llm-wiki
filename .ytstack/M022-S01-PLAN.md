---
milestone: M022
slice: S01
project: llm-wiki
created: 2026-05-17T13:30:37Z
status: done
task_count: 5
completed_tasks: 5
---

# M022-S01 — Slice Plan

**Goal:** `process-inbox.py` archiviert jedes Inbox-Drop zuerst als Original nach `raw/inbox-wiki/<file>` (audit-zone) und erzeugt — wo möglich — zusätzlich ein derived artifact in `raw/<category>/<name>.md` (compile-zone). HTML-`unlink()` wird entfernt. Binary-Drops (audio/pdf) bleiben original-only in `raw/inbox-wiki/`; `raw/audio/` und `raw/papers/` werden vom Inbox-Pfad nicht mehr beschrieben.

## Tasks

- [x] T01 — `INBOX_ARCHIVE_DIR = RAW_DIR / "inbox-wiki"` Constant einführen; `EXTENSION_MAP` neutralisieren (audio/pdf produzieren kein Artifact mehr, nur Original-Archive); CATEGORY_DIRS reduzieren auf Pfade, die echte derived artifacts erzeugen (article, note, transcript).
- [x] T02 — `process_inbox()` umbauen: pro File zuerst `shutil.copy2(file_path, INBOX_ARCHIVE_DIR / file_path.name)`; danach je nach Pfad das Artifact erzeugen. Source-File aus `inbox/` entfernen erst NACHDEM Archive + Artifact erfolgreich geschrieben sind (atomar-ish).
- [x] T03 — ~~HTML-Pfad: `file_path.unlink()` durch Move nach INBOX_ARCHIVE_DIR ersetzen.~~ **Rolled into T02** (die HTML-Branch des process_inbox()-Rewrites). Kein eigener Commit.
- [x] T04 — ~~Binary-Pfad: Move nach INBOX_ARCHIVE_DIR, kein zweiter Schreibvorgang.~~ **Rolled into T02** (die Binary-Branch des process_inbox()-Rewrites). Kein eigener Commit.
- [x] T05 — Tests in `tests/test_process_inbox.py` (oder neu): je 1 Test pro Pfad (md/txt klassifiziert, html extract, mp3 binary, pdf binary) verifiziert Original landet in `raw/inbox-wiki/` UND (falls applicable) Artifact in `raw/<cat>/`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Manueller end-to-end-Probe: 4 Test-Dateien (1 md, 1 html, 1 mp3, 1 pdf) in `inbox/` droppen, `wiki process-inbox` laufen, Resultat im Vault auditen.

## Notes

- HTML-`unlink()`-Stelle ist `scripts/process-inbox.py:148` (verifiziert in dieser Session).
- Verworfener Pfad: für md/txt zusätzlich noch eine Hardlink-Variante (Original und Artifact als gleicher Inode) — zu fragil über Vault-Sync-Backends (iCloud kopiert beim Sync). Echtes Duplikat-File ist der ehrlichere Pfad.
