---
milestone: M022
slice: S02
task: T02
project: llm-wiki
closed: 2026-05-17T14:30:00Z
verification: passed
---

# M022-S02-T02 — Summary

## Outcome

`scripts/collectors/pictures.py` mechanically mirrors T01: `ARCHIVE_SUBDIR` removed, `MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "pictures"` added, three sites updated. Per-image sidecars (`_write_archive_sidecar` writes a `.md` next to the archived `.png` via `archive_path.with_suffix(".md")`) follow into the vault automatically — no special handling needed.

Substrate-output (`raw/notes/pictures/<batch>.md` batch report, `raw/notes/pictures/thumb/*.png` thumbnails) unchanged.

## Deviations from plan

None.

## Follow-ups

- Same lxw-cleanup note as T01: old `<picture_inbox>/.processed/*` content stays orphaned until S03's migration.

## Verification

- `MOBILE_ARCHIVE_DIR` import + path-suffix assertion ✓
- New pictures-test in `tests/test_pictures_collector.py` exercises the routing end-to-end (vision mocked).
- Full pytest suite 835/835.
- Commit: `87a631b` (atomic with T01+T03).
