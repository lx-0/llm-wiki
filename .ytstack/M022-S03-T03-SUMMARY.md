---
milestone: M022
slice: S03
task: T03
project: llm-wiki
closed: 2026-05-17T14:50:00Z
verification: passed
---

# M022-S03-T03 — Summary

## Outcome

`tests/test_migrate_inbox_archive.py` created with 6 pytest cases covering the migration script:

1. **voice** — `.processed/foo.txt` + `.processed/bar.md` migrate into `raw/inbox-mobile/voice/`, legacy folder rmdir-ed.
2. **pictures** — same shape, includes per-image sidecar `.md` alongside the `.png`.
3. **collision** — pre-existing `<dest>/note.txt` is preserved; migrated file gets `note-<mtime>.txt` suffix.
4. **idempotent** — second run finds nothing to migrate, no crash.
5. **unconfigured** — both inboxes unset → graceful skip, no destination dir created.
6. **dry-run** — `--dry-run` flag prevents any move; source and destination both untouched.

Shared `fake_vault` fixture patches `CONFIG.personal.voice_inbox` / `picture_inbox` + `paths.RAW_DIR` at tmp_path, reloads the migration module so module-level imports pick up the patched values.

## Deviations from plan

Plan asked for 4 tests; shipped 6 — added the unconfigured + dry-run cases since both have non-obvious branches that deserve regression coverage.

## Follow-ups

None.

## Verification

- `uv run --project .wiki pytest tests/test_migrate_inbox_archive.py -v` → 6/6 passed.
- Full suite 841/841.
- Commit: `d776e35`.
