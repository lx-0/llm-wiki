---
milestone: M022
project: llm-wiki
size: M
created: 2026-05-17T13:30:37Z
status: done
total_slices: 3
completed_slices: 3
---

# M022 Roadmap

**Goal:** Vereinheitliche das Inbox-Intake-Schema: jedes Channel archiviert das as-arrived Original unter `raw/inbox-<channel>/[<source>/]<file>`; Processoren erzeugen derived artifacts unter `raw/<category>/<name>.md`. Keine `.processed/`-Archive mehr ausserhalb des Vaults.

**Exit criteria:**

- `process-inbox.py` schreibt Original → `raw/inbox-wiki/` + Artifact → `raw/<category>/`; HTML wird nicht mehr `unlink()`-mässig entfernt.
- `voice.py` archiviert Source-Transcript → `raw/inbox-mobile/voice/`; Artifact bleibt in `raw/voice/`.
- `pictures.py` archiviert Source-Bild → `raw/inbox-mobile/pictures/`; Artifact bleibt in `raw/notes/pictures/`.
- compile.py unverändert; `raw/inbox-<channel>/` explizit nicht compiled.
- Migration-Script zieht bestehende `<inbox>/.processed/`-Inhalte auf lxw um.
- 720/720 Tests grün; je Collector ≥1 Test deckt Zwei-Zonen-Write ab.

## Slices

Slice detail lives in per-slice `M022-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 — `process-inbox.py` Zwei-Zonen-Refactor (inbox-wiki original + category artifact, HTML-unlink raus)
- [x] S02 — voice + pictures collectors: Archive-Location nach `raw/inbox-mobile/<source>/`
- [x] S03 — Migration-Script + lxw-Live-Run (T04 verified 2026-05-17T15:44Z, 47 files migrated)

## Slice intent (rough sketch)

- **S01** — `process-inbox.py` Zwei-Zonen-Refactor. Original-write nach `raw/inbox-wiki/` für jeden Drop; Artifact-write nach `raw/<category>/`; HTML-`unlink()` entfernen; `EXTENSION_MAP` audio/papers-Entscheidung treffen. Tests anpassen.
- **S02** — Mobile collectors (`voice.py` + `pictures.py`). `ARCHIVE_SUBDIR`-Konstante durch `raw/inbox-mobile/<source>/`-Pfad ersetzen. Tests anpassen (verifizieren, dass Original im Vault landet, nicht ausserhalb).
- **S03** — Migration + Templates. `scripts/migrations/migrate_inbox_archive.py` zieht lxw-State um (`<voice_inbox>/.processed/*` → `raw/inbox-mobile/voice/`; `<picture_inbox>/.processed/*` → `raw/inbox-mobile/pictures/`). Templates: `raw/inbox-wiki/.gitkeep`, `raw/inbox-mobile/voice/.gitkeep`, `raw/inbox-mobile/pictures/.gitkeep`. `wiki seed --force` testen.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: done` → `status: done` and update global ROADMAP.md
