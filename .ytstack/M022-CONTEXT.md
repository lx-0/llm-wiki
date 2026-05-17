---
milestone: M022
project: llm-wiki
created: 2026-05-17T13:30:37Z
size: M
---

# M022 — Context

## Goal

Vereinheitliche das Inbox-Intake-Schema: jedes Channel archiviert das **as-arrived Original** unter `raw/inbox-<channel>/[<source>/]<file>` im Vault, Processoren erzeugen **derived artifacts** unter `raw/<category>/<name>.md`. Keine `.processed/`-Archive mehr ausserhalb des Vaults; "Rohdaten sind geil"-Prinzip strikt eingehalten.

## Exit criteria

- `scripts/process-inbox.py` schreibt jedes inbox-Item zuerst als Original nach `raw/inbox-wiki/<file>`; danach erzeugt es das derived artifact in `raw/<category>/<name>.md` (Klassifikation per LLM + Frontmatter). HTML-Extraktion (`ingest-html.py`) hängt das `.html`-Original NICHT mehr `unlink()`-mässig ab, sondern lässt es in `raw/inbox-wiki/page.html` liegen.
- `scripts/collectors/voice.py` archiviert das Source-Transcript nach `raw/inbox-mobile/voice/<file>.txt` (statt `<voice_inbox>/.processed/`); punctuated artifact bleibt in `raw/voice/<slug>.md`.
- `scripts/collectors/pictures.py` archiviert das Source-Bild nach `raw/inbox-mobile/pictures/<file>` (statt `<picture_inbox>/.processed/`); vision artifact bleibt in `raw/notes/pictures/<batch>.md`.
- `compile.py` bleibt unverändert (liest nur Category-Folder); `raw/inbox-<channel>/` wird explizit NICHT compiled.
- Migration-Script unter `scripts/migrations/` zieht auf lxw alle bestehenden `<voice_inbox>/.processed/*` + `<picture_inbox>/.processed/*` in die neuen `raw/inbox-mobile/<source>/` Locations um.
- Templates (`templates/raw/.gitkeep` etc.) gespiegelt; `wiki seed --force` legt die neuen Inbox-Folder an.
- 720/720 Tests grün; mindestens je 1 Test pro Collector verifiziert original-zone-write + artifact-zone-write.

## Size

M — 3 Slices, ~7-9 Tasks total. Siehe `M022-ROADMAP.md`.

## Decisions locked in discuss phase

- 2026-05-17: **Zwei-Zonen-Modell.** `raw/inbox-<channel>/` = AS-ARRIVED audit/provenance trail, nie compiled. `raw/<category>/` = derived substrate, immer markdown, compile.py-input. Strikte Trennung — kein Mischen, auch nicht bei md/txt-Drops wo Original und Artifact nahe identisch sind (das Duplikat ist der Preis für die Sauberkeit).
- 2026-05-17: **Channels heute: `inbox-wiki` + `inbox-mobile`.** Channel = Top-Level-Bucket unter `raw/`, Source = optionaler Sub-Bucket darunter. `inbox-mobile` splittet by source (`voice/`, `pictures/`) weil verschiedene File-Typen + verschiedene Processoren. `inbox-wiki` bleibt flat (nur eine source: `<vault>/inbox/`). Künftige Channels: `inbox-mail`, `inbox-browser-share`, ...
- 2026-05-17: **HTML-`unlink()` entfällt.** Heute löscht `process-inbox.py:148` das original-HTML nach erfolgreichem `ingest-html.py`-Lauf. Neu: HTML-Original wandert in `raw/inbox-wiki/page.html`, bleibt erhalten. Symmetrie mit allen anderen Intake-Pfaden.
- 2026-05-17: **`raw/audio/` + `raw/papers/` werden Artifact-only.** Heute sind das Binary-Archive ohne Artifact. Im neuen Modell bleiben Binär-Originale (mp3, m4a, wav, pdf) in `raw/inbox-wiki/`; die Category-Folder werden erst wieder befüllt, wenn ein Processor echte Markdown-Artifacts dort produziert (zukünftige Audio-Transcription / PDF-Extract).
- 2026-05-17: **Voice = text-input, kein audio.** Verified `voice.py:36`: `ACCEPTED_SUFFIXES = (".txt", ".md")`. Voice-Mobile-Channel liefert bereits Transkripte (OpenWhispr/FluidVoice/macOS-Diktat). Post-Processing ist Punctuation + Slug + Frontmatter, kein binary→text extract.
- 2026-05-17: **Voice + Pictures behalten heutige Artifact-Locations.** `raw/voice/<slug>.md` und `raw/notes/pictures/<batch>.md` bleiben wo sie sind — nur die ARCHIVE-Location des Originals zieht von `<inbox>/.processed/` nach `raw/inbox-mobile/<source>/`.

## Open questions

- Soll der `inbox-wiki/`-Archiv-Pfad pro Datei auch in der Artifact-Frontmatter referenziert werden (`source_file: raw/inbox-wiki/note.md`)? Erlaubt Re-Compile aus dem Original, falls das Artifact je verloren geht. — entscheiden während S01.
- Behalten wir `EXTENSION_MAP` für audio (heute `→ raw/audio/`)? Im neuen Modell zieht das Audio einfach nach `raw/inbox-wiki/memo.mp3` und es entsteht KEIN Artifact. Sauberer wäre, `EXTENSION_MAP` für audio zu entfernen und einfach "binary ohne processor" → original-only-archive zu machen. — entscheiden während S01.
- ~~Migration auf lxw: dürfen wir per Script `<voice_inbox>/.processed/` aufräumen (rmdir nach move)?~~ **Entschieden 2026-05-17:** auto-rmdir nach erfolgreichem Move. iCloud-`.processed/` verschwindet komplett; ab dem nächsten Collector-Run ist die Vault-Archive-Location die einzige Dedup-Quelle.
