---
milestone: M025
slice: S01
project: llm-wiki
created: 2026-05-23T08:53:30+0200
status: planned
task_count: 3
completed_tasks: 0
---

# M025-S01 -- Slice Plan

**Goal:** Captures dropped via the file-drop door land in `raw/captures/` with a
stable, deterministic capture-ID in frontmatter, and a Python-side index maps each
capture-ID to its source path. Pure capture-side spine -- no compile/agent changes.

## Tasks

- [ ] T01 -- `scripts/collectors/capture_collector.py` modeled on `voice.py`:
  folder-watch on `personal.capture_inbox`; assign a deterministic stable
  capture-ID per capture (content+timestamp hash, idempotent on re-drop); write a
  frontmatter-stamped note (`capture_id:`, `type: capture`) into `raw/captures/`;
  two-zone archive of the source (voice.py `MOBILE_ARCHIVE_DIR` pattern). Unit
  tests: ID determinism + idempotent re-run + frontmatter shape + archive move.
- [ ] T02 -- Config + registration + migration + template sync (HARD rule:
  config change ⇒ migration same commit). Add `personal.capture_inbox` +
  `piggybacks.capture` (enabled/cooldown) to `scripts/core/config.py` +
  `config.example.yaml`; register the collector in the Registry with
  `piggyback_default`; add the keys to `scripts/migrations/migrate_config_keys.py`;
  sync `templates/`. Unit test: migration injects the new keys.
- [ ] T03 -- Capture index: deterministic `state/capture_index.json` mapping
  `capture_id → {source_path, created, status: "open"}`, written at ingest. This is
  the bridge S02 (forward link) and S03 (supersede) both consume. Unit tests: index
  updated on ingest, idempotent re-run, entry survives source re-ingest.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- Capture surface is deliberately the existing file-drop (operator's choice of
  one-tap door); the ID + index mechanics are surface-agnostic. Do NOT build a new
  capture UI (locked in M025-CONTEXT).
- Naming: `capture_collector.py` (not `capture.py`) to stay clear of any import
  shadowing convention; Registry name stays `capture`.
