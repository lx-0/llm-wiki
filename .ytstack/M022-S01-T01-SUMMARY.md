---
milestone: M022
slice: S01
task: T01
project: llm-wiki
closed: 2026-05-17T13:55:00Z
verification: passed
---

# M022-S01-T01 — Summary

## Outcome

- `scripts/core/paths.py`: added `RAW_INBOX_WIKI_DIR = RAW_DIR / "inbox-wiki"` (line 41).
- `scripts/process-inbox.py`: import line trimmed (`RAW_AUDIO_DIR` + `RAW_PAPERS_DIR` removed, `RAW_INBOX_WIKI_DIR` added); `EXTENSION_MAP` rerouted from per-extension category strings (audio/papers) to a single sentinel `"binary"`; `CATEGORY_DIRS` reduced to three artifact-emitting categories (article/note/transcript).
- Pure prep — no behavior change until T02 lands the new flow in `process_inbox()`. Marked in T01-PLAN as "must ship atomic with T02".

## Deviations from plan

None. Plan matched implementation 1:1.

## Follow-ups

- `RAW_AUDIO_DIR` and `RAW_PAPERS_DIR` still defined in `paths.py:42-46` even though no callsite imports them anymore. Removal deferred to M022-S01-T05 (or a later sweep) once nothing else references them.
- `add_frontmatter()`'s body still uses the legacy `type:` frontmatter key — not touched here. Compile-zone artifact metadata (channel: inbox-wiki, source-file, ingested_at) is a M022-S01-T05 / out-of-slice concern.

## Verification

- `uv run --project .wiki python -c "from core.paths import RAW_INBOX_WIKI_DIR; print(RAW_INBOX_WIKI_DIR)"` → `…/lx-0/raw/inbox-wiki` ✓
- Import-shape assertion: `EXTENSION_MAP.values() == {"binary"}` ✓, `CATEGORY_DIRS.keys() == {"article", "note", "transcript"}` ✓
- Full pytest suite: 824/824 passed (no regressions — existing tests cover helpers, not the routing logic that was reshaped)
- Commit: `c51494a` (T01+T02 atomic landing)
