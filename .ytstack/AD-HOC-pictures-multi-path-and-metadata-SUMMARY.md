# AD-HOC — pictures multi-path + EXIF/filename metadata + dep-sync fix (2026-05-29)

**Trigger:** Inbox-bridge slice (`9e544bb`, same session) had landed the rsync mirror
to `~/wiki-inbox-local/screenshots-tablet/` but the pictures collector only accepted
a single inbox path, so the operator could not feed Drive-bridge output into a
collector that was already wired to the iCloud inbox. After picture_inbox was lifted
to multi-source, the operator asked what the metadata sidecars carry — and noted that
camera/location/device info from the original files would be valuable. Three arcs
followed inside the same session, plus two infrastructure fixes the third surfaced.

## Arc 1 — `picture_inbox: str | list[str]` (commit `e9a7fe9`)

The substrate collectors took one inbox path each. The bridge ships file mirrors,
so any operator who wanted to add a second source (Drive bridge alongside an
existing iCloud Drive folder) had to either choose-one or symlink the two
together. Solution: relax `Personal.picture_inbox` to accept both shapes
(`str | list[str]`). Single-string operators are unchanged. List operators
get every configured path scanned per run, missing paths log WARNING and are
skipped, results aggregate chronologically into a single batch report.

13 unit tests on `_inbox_paths`, `is_configured`, and `run()` cover both shapes
plus edge cases (blanks in the list, all-missing, expansion). Migration not
needed — type relaxation is back-compat at the YAML layer. `config.example.yaml`,
`docs/setup-pictures.md`, and `docs/setup-bridge.md` show the multi-path stanza.

## Arc 2 — picture-metadata extraction (commit `d083b45`)

The operator asked for camera / location / device info in the sidecars.
Building this surfaced that for Android-tablet screenshots the EXIF block is
nearly empty (only `Software` with a device-code hint, no GPS, no
`DateTimeOriginal`), while the **filename** encodes both the capture timestamp
and the app the user was viewing (`Screenshot_YYYYMMDD_HHMMSS_<AppContext>.jpg`).
For real camera photos (future iPhone JPEGs through iCloud, dedicated camera
JPEGs) EXIF is the bigger payload: GPS as decimal degrees, Make/Model, shot
parameters (FNumber/ExposureTime/ISO/FocalLength).

Built `scripts/collectors/_picture_metadata.py` combining both sources:
EXIF via Pillow (JPEG/PNG native) + Android-screenshot filename regex.
captured_at priority: EXIF DateTimeOriginal → filename → file mtime.
The pictures collector calls `extract_metadata()` in `run()` before the
gemma4 vision pass; deterministic metadata is **orthogonal** to LLM output
and lands in the same sidecar frontmatter:

```yaml
captured_at: 2024-09-05T17:17:58
device:
  software: "Android UP1A.231005.007.X200XXS3DXD5"
location:                  # only when EXIF GPS present
  lat: 51.507400
  lon: -0.127800
  alt: 35.0
shot:                      # camera photos only
  aperture: 1.8
  exposure: "1/120"
  iso: 100
  focal_length_mm: 28
app_context: "O'Reilly"    # Android-screenshot filename only
```

Empty sub-dicts and missing keys are omitted, so each sidecar carries exactly
what was extractable. HEIC is deferred (needs `pillow-heif` extra). Knob:
`features.extract_picture_metadata`, default `True`, flip false for privacy.

`scripts/backfill_picture_metadata.py` + `wiki backfill picture-metadata` walk
`raw/inbox-mobile/pictures/*.md`, find each sidecar's matching original
image, and merge the deterministic keys into FM without touching existing
ones. Per-key idempotence — re-run after a missing dep ships picks up the
previously-skipped EXIF without re-walking already-present filename data.
16 unit tests on the extractor cover the two sources, the merge order,
and the EXIF graceful-fallback paths.

## Arc 3 — Pillow as explicit dep + `wiki update` runs `uv sync` (commits `5024f1d` + `fd47c5f`)

Live-verifying the first backfill run against lxw surfaced REGEL #1 drift:
49 Android-screenshot sidecars all got `captured_at` + `app_context`, but
**zero** got `device.software`. Diagnosis: `_parse_exif()` catches
`ImportError` for PIL and returns `{}` — a graceful fallback designed for
the case where Pillow isn't available. The engine repo's venv had Pillow
12.2.0 (transitive of yt-dlp on macOS), but the **vault venv** did not;
fresh `uv sync` on the operator's vault never picked it up. The
"graceful agnostic" pattern was correct on principle but turned the feature
into a silent always-off on every existing vault.

Two fixes in series:
- Declare `pillow>=10.0.0` explicitly in `pyproject.toml` — accidental
  transitive availability is not portable across uv resolutions, and Pillow
  is small enough to ship as a hard dep (~6 MB).
- Add `uv sync --project "$WIKI_DIR" --quiet` to `cmd_update()` right after
  the git pull. Without this, `wiki update` git-pulled a new pyproject.toml
  but never refreshed the venv — silent feature-disable on every dep
  change. Pre-existing footgun, not specific to this feature. Catch-22
  during initial bootstrap: the running `wiki update` invocation predates
  the patch, so the FIRST update after the change still doesn't sync.
  Operator one-shot: `uv sync --project <vault>/.wiki` once manually,
  then future updates take care of themselves.

The backfill marker design also flipped from coarse to per-key idempotence
(`2e45954`). The original `BACKFILL_MARKER_KEYS = ("device", "location",
"shot", "app_context")` early-skipped any sidecar that had even ONE of
those keys — wrong for the "Pillow gets installed later" case. Dropped
the early-skip; the per-key merge `if key in fm: continue` already does
the right thing on its own.

## Files

| File | Change |
|------|--------|
| `scripts/core/config.py` | `picture_inbox: str \| list[str]`; new `features.extract_picture_metadata: bool = True` |
| `scripts/collectors/pictures.py` | `_inbox_paths()` list-form; calls `extract_metadata` in `run()`; new `_render_picture_metadata_block` rendering optional FM keys; `captured_at` from EXIF/filename when available |
| `scripts/collectors/_picture_metadata.py` | new; Pillow EXIF parse + Android filename regex; GPS DMS→decimal; graceful ImportError fallback |
| `scripts/backfill_picture_metadata.py` | new; `wiki backfill picture-metadata` entry; per-key idempotence |
| `scripts/migrations/migrate_config_keys.py` | inject `features.extract_picture_metadata: True` |
| `wiki` | new `cmd_backfill` dispatcher; `cmd_update` now runs `uv sync` |
| `config.example.yaml`, `docs/setup-pictures.md`, `docs/setup-bridge.md` | documentation |
| `pyproject.toml` + `uv.lock` | explicit `pillow>=10.0.0` |
| `tests/test_pictures_multi_inbox.py` (13) + `tests/test_picture_metadata.py` (16) | new |
| `tests/test_migrate_config_keys.py` | counter +1 / fixture sync |
| `.ytstack/AD-HOC-drive-inbox-bridge-SUMMARY.md` | Arc 0 (already written this session) |

## Verified (REGEL #1)

- Unit tests: 16 metadata + 13 multi-path + 16 bridge + 47 migration all green.
- Live-probed `extract_metadata()` against `Screenshot_20240905_171758_O'Reilly.jpg`:
  `captured_at=2024-09-05T17:17:58`, `app_context="O'Reilly"`,
  `device.software="Android UP1A.231005.007.X200XXS3DXD5"` extracted as
  expected.
- Vault end-to-end: bridge sync rsync'd 49 Android screenshots from Drive to
  `~/wiki-inbox-local/screenshots-tablet/`; pictures collector consumed both
  inboxes; backfill (after Pillow landed in vault venv) updated 49/49
  Screenshot sidecars with `device.software` field. Verified by reading the
  O'Reilly sidecar post-fix — three new keys present.

## Operator-side gates

- `wiki bridge sync` must run from the operator's shell (LaunchAgent later),
  not from a Claude-Code-spawned subprocess — Claude Code is itself
  TCC-blocked on `~/Library/CloudStorage/`. Bridge LaunchAgent template
  shipped (`templates/.launchd/com.llm-wiki.bridge.plist.template`).
- First `wiki update` after the `uv sync` patch still uses the OLD update
  binary (loaded pre-pull). One-shot manual `uv sync --project <vault>/.wiki`
  after that bootstrap; subsequent updates self-heal.

## Out of scope / backlog

- HEIC support (`pillow-heif`) — deferred.
- iCloud-Drive JPEGs in `2026-05-17-*` sidecars are EXIF-stripped (iOS
  Shortcut / AirDrop likely the cause). Backfill yields no-op on them.
  Not the engine's problem; operator-side capture path adjustment.
- System-level scheduler — separate backlog
  (`.ytstack/backlog/system-level-scheduler.md`), surfaced this session.
  The bridge LaunchAgent is the first of N plists that pattern would
  consolidate behind a `wiki scheduler install` verb.

## Commits

- `e9a7fe9` feat(pictures): accept list[str] for picture_inbox (multi-source intake)
- `d083b45` feat(pictures): EXIF + Android-filename metadata in archive sidecars
- `5024f1d` fix(deps): declare pillow explicitly for EXIF extraction
- `2e45954` fix(backfill): per-key idempotence, drop coarse already-backfilled gate
- `fd47c5f` fix(update): run uv sync so pyproject.toml changes reach vault venv

All on origin/main.
