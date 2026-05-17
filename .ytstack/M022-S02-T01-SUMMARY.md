---
milestone: M022
slice: S02
task: T01
project: llm-wiki
closed: 2026-05-17T14:30:00Z
verification: passed
---

# M022-S02-T01 — Summary

## Outcome

`scripts/collectors/voice.py` archive-location relocated from `<voice_inbox>/.processed/` (iCloud Drive, outside the vault) to `raw/inbox-mobile/voice/` (vault audit zone). Mechanics:
- `ARCHIVE_SUBDIR = ".processed"` removed
- `MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "voice"` added at module scope
- Three archive sites (setup, empty-file branch, normal-ingest branch) all point at `MOBILE_ARCHIVE_DIR`
- Module + class docstrings updated to advertise the new location

Substrate-output (`raw/voice/<slug>.md`) unchanged. Dedup-as-move mechanics unchanged.

## Deviations from plan

None.

## Follow-ups

- Once `wiki update` rolls M022 out to lxw, the operator's first voice-collector run will write to the vault. Old files in `<voice_inbox>/.processed/` stay orphaned until S03's migration script runs — they don't break anything but they're junk.

## Verification

- `MOBILE_ARCHIVE_DIR` import + path-suffix assertion ✓
- Full pytest suite 835/835 (post T03 fixes to existing voice tests).
- Commit: `87a631b` (atomic with T02+T03).
