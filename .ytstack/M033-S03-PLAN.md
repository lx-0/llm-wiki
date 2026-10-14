---
milestone: M033
slice: S03
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 6
completed_tasks: 1
---

# M033-S03 -- Slice Plan

**Goal:** The helpers that grew next to the 0.3.0 seams fold back onto them — one frontmatter grammar, one slugify, one logging setup, state through `core/state_store`, one daily-rollup appender, one inbox scanner — each migration preceded by a consumer grep and covered by the seam's existing tests plus a parity test on the old behaviour.

## Tasks

- [x] T01 -- Frontmatter, top-level scripts (9 of 17): `pin.py`, `web_research.py`, `backfill_picture_metadata.py`, `backfill_daily_rollup.py`, `dedup.py`, `health_trends.py`, `reconcile.py`, `lint.py`, `dream.py` delegate to `core/frontmatter.parse` / `field` / `split_fence`; a parity test per site runs the old function's fixtures through the seam first (differences are decisions, recorded).
- [ ] T02 -- Frontmatter, packages (8 of 17): `menu_context._read_frontmatter_field`, `compile_stages/route.py`, `collectors/gmeet.py`, `core/agent_spec.py`, `core/prompts.py`, `facts/correct.py`, `facts/take.py`, `reports/_engine/lib/timeline.py` — same method; afterwards `grep -rn "def _\?\(read\|parse\|split\)_frontmatter" scripts` prints only `core/frontmatter.py`.
- [ ] T03 -- Slugify 5 → 1: `core/utils.slugify` gains whatever `scan_youtube.slugify` and the byte-identical `_slugify(text, max_len=60)` in `jamie` / `calendar_collector` / `gmeet` need (max-length semantics compared on their fixtures — filenames in operator vaults must not change: parity test over the real `raw/` filename patterns), callers switched.
- [ ] T04 -- Logging → one setup: `preprocessors/cli`, `producers/cli`, `collectors/cli`, `bridge/cli` `_setup_logging` replaced by `core/console.setup_console_logging` (idempotent — KNOWLEDGE "lazy-import CLI module = doubled stderr"); then the inventory S02 left behind — 36 files call `logging.basicConfig` (`grep -rln 'logging.basicConfig' scripts`): the CLIs and the entry scripts go through the seam, a one-shot migration / backfill may keep a `__main__`-local call only where the seam cannot serve it (recorded per file); and the six modules whose console setup sits before their imports (`noqa: E402` in `compile`, `menu`, `query`, `review_wiki`, `optimize_claude_md`, `collectors/scan_screenshots`) end with their imports at the top, because the seam imports cleanly. stderr parity checked on the oracle. Split at plan-task if the sweep does not fit one context window.
- [ ] T05 -- State through the store: `email_collector`, `scan_screenshots`, `folder_index` `_load_state` / `_save_state` replaced by `core/state_store.store_for` (lock + atomic write), watermark semantics proven by the collectors' existing tests plus one race test per site mirroring `tests/test_state_store.py`.
- [ ] T06 -- Collector inbox + rollup 3 → 1: `voice`, `capture_collector`, `pictures` `_scan_inbox` / `_append_daily_rollup` fold into one shared helper (`core/daily_capture` or a `collectors/_inbox.py` — chosen by where the sentinel-block logic already lives), with the per-collector rollup headings preserved byte-for-byte on their fixtures; `templates/` resynced if a rollup shape is touched.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `print(` vs logging (529 vs 746) is out of this slice: too broad to be one task and not an exit criterion; it is a M034 candidate when the CLI output moves to Python entirely.
- Each task's commit message names the sites it folded and quotes the before/after grep count — the "unused only after a repo-wide grep" rule is the gate for every deletion.
- 2026-10-14 (T01 planning): the repo-wide grep (`def _?[a-z_]*frontmatter[a-z_]*\(`) finds more reader sites than the audit's 17 — for T01 a tenth top-level one (`cleanup_legacy_daily_roots._has_digest_frontmatter`); for T02 beyond its eight: `compile_stages/classify._frontmatter_type`, `core/utils._parse_fact_frontmatter`, `reports/_engine/lib/verify_report._extract_frontmatter`, `core/links._strip_frontmatter_and_fences` (fence split only), and the test-local `_split_frontmatter` in `tests/reports/test_runner_report.py`. The writers (`preprocessors/inbox.add_frontmatter`, `voice` / `capture_collector` `_build_frontmatter`, `healthkit_xml.to_frontmatter`) are builders, not parsers — T02 checks them against `serialize` and records which stay. `lint.py` is already on the seam (C03).
- 2026-10-14 (reassess after S02): T04 widened to the `basicConfig` inventory S02 found (see the task line). Not in this slice: lazy collector registration (`backlog/lazy-collector-registry.md`, M034) — the `collectors` package imports every module to register it; S03's folds inside collectors (T05, T06) must not add module-level work to that import.
