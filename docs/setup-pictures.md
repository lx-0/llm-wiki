# Pictures intake setup

The pictures collector (`scripts/collectors/pictures.py`) ingests camera
and phone photos from an inbox directory. It runs each image through
the local gemma4 vision model (Ollama @ `models.ollama_url`) using a
photo-shaped prompt — scene description, objects, action, visible text,
setting — and emits a per-batch markdown report under
`raw/notes/pictures/`. Sources are archived under `<inbox>/.processed/`
next to a per-image sidecar so the analysis is re-findable from the
archive without grepping batch reports.

Accepts `.jpeg` / `.jpg` / `.png` / `.heic`. HEIC is transcoded
transparently by macOS `sips`.

## 1. Pick an inbox path

For **mobile-first capture** (iPhone is the realistic capture surface),
put the inbox under iCloud Drive so an iOS Shortcut or AirDrop can
deposit photos:

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/inbox/pictures
```

On iOS this shows up in the Files app as `iCloud Drive → inbox →
pictures`. A Shortcut configured with the **Save File** action and the
"Ask Where to Save = off" option drops directly into this folder.

For **Mac-only capture**, any local path works:

```bash
mkdir -p ~/Pictures/llm-wiki-inbox
```

## 2. Wire it in `config.yaml`

In `<vault>/.wiki/config.yaml`:

```yaml
personal:
  picture_inbox: "~/Library/Mobile Documents/com~apple~CloudDocs/inbox/pictures"
  # or: picture_inbox: "~/Pictures/llm-wiki-inbox"
```

As of 2026-05-28 `picture_inbox` also accepts a **list** of paths —
useful when combining an iCloud-Drive folder with an
[`inbox_bridges`](setup-bridge.md)-mirrored Google Drive folder:

```yaml
personal:
  picture_inbox:
    - "~/Library/Mobile Documents/com~apple~CloudDocs/inbox/pictures"
    - "~/wiki-inbox-local/screenshots-tablet"
```

Every path is scanned per run, results aggregate into a single batch
report (ordered chronologically by file mtime across sources). Paths
that don't exist (Drive offline, bridge hasn't run yet) log a WARNING
and are skipped without aborting the others.

The piggyback is on by default with a 6 h cooldown and a 20-images-per-run
cap. To tune or disable:

```yaml
piggybacks:
  pictures:
    enabled: true
    cooldown_hours: 6
    max_per_run: 20
```

## 3. Point a capture source at the inbox

### iOS Shortcut — Share Sheet → save to inbox (mobile primary)

1. Shortcuts → +, choose **Receive Photos from Share Sheet** as input.
2. Action: **Save File**. Destination: `iCloud Drive → inbox → pictures`,
   "Ask Where to Save" = **off**.
3. Filename: `Current Date` with format `yyyy-MM-dd-HHmmss` and the
   original photo's extension. This matches the timestamp parser in
   `pictures.py`.
4. Run from the Camera-Roll share sheet, or pin the Shortcut to the
   Action Button for one-press capture.

iCloud syncs to the Mac within ~30 s; the collector picks the new file
up on the next piggyback or `wiki collect pictures`.

### AirDrop / manual copy (desktop)

Drop files directly into the inbox folder. The collector ignores
dot-files, the `.processed/` archive subfolder, and unknown extensions.

## 4. What lands where

```
<picture_inbox>/2026-05-17-093839.jpeg    ← drop target
       ↓ wiki collect pictures
<picture_inbox>/.processed/2026-05-17-093839.jpeg   ← archived original (moved, not copied — same iCloud footprint)
<picture_inbox>/.processed/2026-05-17-093839.md     ← per-image sidecar with full vision analysis

<vault>/raw/notes/pictures/pictures-2026-05-17T0943.md   ← batch report (compile substrate)
<vault>/raw/notes/pictures/thumb/2026-05-17-093839.jpeg  ← 384px thumb (Obsidian embed)
<vault>/daily/2026-05-17/pictures.md                     ← daily-rollup one-liner per intake
```

## 5. CLI

```
wiki collect pictures --dry-run     # show what would happen
wiki collect pictures               # ingest + archive
wiki collect --list                 # registry snapshot incl. is_configured
```

## 6. Compile dispatch

The batch report's frontmatter carries `type: picture-batch`. `compile.py`
routes it to `compile_pictures.md` (Haiku 4.5, 20-turn budget). The
compile prompt is deliberately ruthless about anti-noise — most camera
photos are NOT knowledge artifacts, and the typical batch produces 0
new wiki entries. Strong "keep" signals are visible text (whiteboards,
receipts, document scans) or scenes matching an existing
project / concept / person page. Everything else gets archived but not
indexed.

## See also

- Prompt: [`prompts/scan_pictures_vision.md`](../prompts/scan_pictures_vision.md) — the per-image vision prompt
- Prompt: [`prompts/compile_pictures.md`](../prompts/compile_pictures.md) — the batch → knowledge extraction prompt
- Memory file: `project_pictures_collector_shipped.md` — design history and rejected alternatives
