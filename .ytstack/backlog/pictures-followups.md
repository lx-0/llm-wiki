# Pictures collector — follow-ups post-2026-05-17 ship

Pictures intake shipped 2026-05-17 (commits `2a2498b` engine + `81013ea` dedicated prompt + `84b3500` thumb-dir fix + `f658b70` daily_capture `KNOWN_SOURCES`). End-to-end live-verified on lxw with 8 keep-rated photos (lego model + 7 nutrition-label scans). Open work below.

## 1. HEIC ingest path — untested (REGEL #1)

`ACCEPTED_SUFFIXES` includes `.heic` and the resize step uses macOS `sips` which natively transcodes HEIC → PNG. No live HEIC sample has hit the inbox so far — all production drops have been `.jpeg`. If the iOS Shortcut ever writes HEIC (camera setting "High Efficiency"), the first one through will be the test.

Verification: drop one `.heic` into `inbox/pictures/`, run `wiki collect pictures`, confirm vision call succeeds and thumb renders. If sips errors, fallback options:

- ImageMagick `magick convert input.heic output.png`
- Pre-convert in the iOS Shortcut (add "Convert Image" action with format=JPEG before "Save File")

No code change pre-flight — wait for first HEIC drop and observe.

## 2. Archive policy — pictures grow iCloud footprint linearly

Current: `shutil.move()` archives 6 MB JPEGs into `<picture_inbox>/.processed/`. Storage net-neutral (move not copy) but the archive accumulates ~2 GB / year at one photo / day.

Options (from the 2026-05-17 AskUser before user picked "move-keep"):

a. **Keep current** — move into `.processed/`. Re-processing possible, original auditable, sidecar as index.
b. **Delete-after-process** — `os.unlink(src)` after sidecar + thumb + report write. Vault keeps only the 384px thumb. Flat iCloud footprint, but no re-processing and no original.
c. **Move out-of-iCloud** — `shutil.move()` to `~/Pictures/llm-wiki-archive/`. Original preserved, iCloud flat, but archive single-device-only (not visible from iPhone).
d. **Compression tier** — archive original at reduced quality (`sips --setProperty formatOptions 60`) yielding ~1.5 MB instead of 6 MB. ~4× footprint reduction without losing the original entirely.

Trigger to revisit: iCloud-Drive nag from Apple about storage, OR explicit operator threshold (`du -sh inbox/pictures/.processed` > 5 GB).

## 3. Diagrams not updated

Per memory `feedback_infographics_track_engine`: reliability/feature changes must hit both `docs/architecture.excalidraw` + `docs/overview.excalidraw` in the same arc as the code. The 2026-05-17 pictures ship skipped this — diagrams still show only 10 collectors, no pictures node.

Render-aware follow-up:

- Add a `pictures` node next to `screenshots` in `docs/architecture.excalidraw` (both feed `compile.py` via the same `picture-batch` / `screenshot-batch` SUBSTRATE_PROMPTS dispatch line).
- Add a `pictures` input box in `docs/overview.excalidraw` next to `voice` (mobile-primary capture surfaces).
- Apply the three excalidraw-pitfalls from `.ytstack/KNOWLEDGE.md` (boundElements `[]` not `null`; `index` field required; render same theme as production PNG).

Re-render both PNGs after edits via `skills/excalidraw-diagram/references/render_excalidraw.py`.

## 4. Compile-pass on a picture-batch — untested

`SUBSTRATE_PROMPTS["picture-batch"] → compile_pictures` is wired (`compile.py` + `prompts/compile_pictures.md`) but no compile run has consumed a real `pictures-*.md` yet. The 8 batched-keep nutrition photos from 2026-05-17 are sitting in `raw/notes/pictures/` waiting for the next flush trigger.

Expected behavior (per prompt design): aggressive anti-noise filter. Most rows are nutrition labels with strong `text_visible` → maybe one fact-stub for one supplement, otherwise zero new entries. Watch first compile to confirm the noise floor holds.
