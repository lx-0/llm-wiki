---
milestone: M025
slice: S02
project: llm-wiki
created: 2026-05-23T08:53:30+0200
status: done
task_count: 3
completed_tasks: 3
---

# M025-S02 -- Slice Plan

**Goal:** The loop becomes observable -- the digest shows each recent capture keyed
by ID with how the brain read it, and a capture that references a known ID is
recognized as a correction. No compile/agent changes (the forward link is resolved
Python-side via `compiled_from`).

## Tasks

- [x] T01 -- `capture_id → article` resolution (Python, no compile change): scan
  `knowledge/**` frontmatter `compiled_from` and join against the S01 capture index
  (`capture_id → source_path`) to produce `capture_id → article_path`. Expose a
  helper (e.g. `core/capture_index.resolve_articles()`). Unit test on a fixture
  corpus (capture source → compiled article with `compiled_from`).
  → `core/capture_index.resolve_articles()` (2026-06-25, 9 tests). See
  `M025-S02-T01-SUMMARY.md`.
- [x] T02 -- Digest "Captures" section: extend `scripts/daily_digest_runner.py` +
  the `daily-digest` prompt (in `prompts/`) to render recent captures keyed by
  `capture_id` → interpretation (linked article) + the context the brain added.
  Integration test on a fixture (capture + resolved article → expected digest rows).
  → built DETERMINISTICALLY (`build_captures_section()` + runner injection), prompt
  only suppresses agent double-coverage (2026-06-25, 15 tests). See
  `M025-S02-T02-SUMMARY.md`. Rendered-digest obedience operator-verified.
- [x] T03 -- Correction recognition (capture-side only): a capture body referencing
  a known capture-id (`re:<id>` / `corrects:<id>` leading token) gets
  `kind: correction` + `corrects: <id>` frontmatter, distinct from a fresh capture.
  Add `docs/setup-captures.md` documenting the drop + correction syntax. Unit tests:
  correction vs fresh detection, unknown-id falls back to fresh capture.
  → `detect_correction()` + collector tagging + `docs/setup-captures.md` (2026-06-25,
  39 tests). See `M025-S02-T03-SUMMARY.md`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- T01 deliberately resolves the forward link Python-side so S02 does NOT depend on
  S03's compile changes (sequential slices must not forward-depend).
- The supersede *effect* of a correction is S03 -- here we only detect and tag it.
