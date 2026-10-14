---
milestone: M033
slice: S03
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 7
completed_tasks: 5
---

# M033-S03 -- Slice Plan

**Goal:** The helpers that grew next to the 0.3.0 seams fold back onto them — one frontmatter grammar, one slugify, one logging setup, state through `core/state_store`, one daily-rollup appender, one inbox scanner — each migration preceded by a consumer grep and covered by the seam's existing tests plus a parity test on the old behaviour.

## Tasks

- [x] T01 -- Frontmatter, top-level scripts (9 of 17): `pin.py`, `web_research.py`, `backfill_picture_metadata.py`, `backfill_daily_rollup.py`, `dedup.py`, `health_trends.py`, `reconcile.py`, `lint.py`, `dream.py` delegate to `core/frontmatter.parse` / `field` / `split_fence`; a parity test per site runs the old function's fixtures through the seam first (differences are decisions, recorded).
- [x] T02 -- Frontmatter, packages (8 of 17): `menu_context._read_frontmatter_field`, `compile_stages/route.py`, `collectors/gmeet.py`, `core/agent_spec.py`, `core/prompts.py`, `facts/correct.py`, `facts/take.py`, `reports/_engine/lib/timeline.py` — same method; afterwards `grep -rn "def _\?\(read\|parse\|split\)_frontmatter" scripts` prints only `core/frontmatter.py`.
- [x] T03 -- Slugify 5 → 1: `core/utils.slugify` gains whatever `scan_youtube.slugify` and the byte-identical `_slugify(text, max_len=60)` in `jamie` / `calendar_collector` / `gmeet` need (max-length semantics compared on their fixtures — filenames in operator vaults must not change: parity test over the real `raw/` filename patterns), callers switched.
- [x] T04 -- Logging → one setup: `preprocessors/cli`, `producers/cli`, `collectors/cli`, `bridge/cli` `_setup_logging` replaced by `core/console.setup_console_logging` (idempotent — KNOWLEDGE "lazy-import CLI module = doubled stderr"); then the inventory S02 left behind — 36 files call `logging.basicConfig` (`grep -rln 'logging.basicConfig' scripts`): the CLIs and the entry scripts go through the seam, a one-shot migration / backfill may keep a `__main__`-local call only where the seam cannot serve it (recorded per file); and the six modules whose console setup sits before their imports (`noqa: E402` in `compile`, `menu`, `query`, `review_wiki`, `optimize_claude_md`, `collectors/scan_screenshots`) end with their imports at the top, because the seam imports cleanly. stderr parity checked on the oracle. Split at plan-task if the sweep does not fit one context window.
- [x] T05 -- State through the store: `email_collector`, `scan_screenshots`, `folder_index` `_load_state` / `_save_state` replaced by `core/state_store.store_for` (lock + atomic write), watermark semantics proven by the collectors' existing tests plus one race test per site mirroring `tests/test_state_store.py`.
- [ ] T06 -- Collector inbox + rollup 3 → 1: `voice`, `capture_collector`, `pictures` `_scan_inbox` / `_append_daily_rollup` fold into one shared helper (`core/daily_capture` or a `collectors/_inbox.py` — chosen by where the sentinel-block logic already lives), with the per-collector rollup headings preserved byte-for-byte on their fixtures; `templates/` resynced if a rollup shape is touched.
- [ ] T07 -- Frontmatter, the unnamed sites: the fence grammars T02's name-based guard could not see — `collectors/health.py` (`_FRONTMATTER_RE`, the HealthKit merge read), `collectors/calendar_collector.py` (two inline `startswith("---\n")` / `find("\n---\n")` probes), `core/capture_index.py` (`_FM_RE`), `core/daily_capture.py` (`_FRONTMATTER_RE` in `_read_sources_and_body`), `core/utils.py` (the `compile_role: final-only` probe), `dashboard/dashboard_stats.py` (the same probe), `migrations/migrate_add_type.py` (`_FRONTMATTER_RE` + `_TYPE_LINE_RE`), `suggestions/cli.py` (`load_suggestion`'s fence strip) — each onto `split_fence` / `field` / `parse` with its contract kept; then the guard in `tests/test_frontmatter_parity.py` scans every function (not only `*frontmatter*`-named ones) for fence smells, with `lint.py`'s body-separator scan allow-listed by reason. Exit criterion 5 ("0 private parsers") is measured by that widened guard, not by T02's.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `print(` vs logging (529 vs 746) is out of this slice: too broad to be one task and not an exit criterion; it is a M034 candidate when the CLI output moves to Python entirely.
- Each task's commit message names the sites it folded and quotes the before/after grep count — the "unused only after a repo-wide grep" rule is the gate for every deletion.
- 2026-10-14 (T01 planning): the repo-wide grep (`def _?[a-z_]*frontmatter[a-z_]*\(`) finds more reader sites than the audit's 17 — for T01 a tenth top-level one (`cleanup_legacy_daily_roots._has_digest_frontmatter`); for T02 beyond its eight: `compile_stages/classify._frontmatter_type`, `core/utils._parse_fact_frontmatter`, `reports/_engine/lib/verify_report._extract_frontmatter`, `core/links._strip_frontmatter_and_fences` (fence split only), and the test-local `_split_frontmatter` in `tests/reports/test_runner_report.py`. The writers (`preprocessors/inbox.add_frontmatter`, `voice` / `capture_collector` `_build_frontmatter`, `healthkit_xml.to_frontmatter`) are builders, not parsers — T02 checks them against `serialize` and records which stay. `lint.py` is already on the seam (C03).
- 2026-10-14 (T02): the acceptance "the def-name grep prints only `core/frontmatter.py`" is replaced by the precise form — `tests/test_frontmatter_parity.py::test_no_private_frontmatter_grammar_outside_the_seam`: no top-level `*frontmatter*` function outside the seam may read a fence with a grammar of its own (`yaml.safe_load`, a fence regex, `startswith("---`, `find("\n---`). Read-wrappers that call the seam (T01's four, `take`, the C03 accessors in `route` / `classify`) and the three hand-built WRITERS (`voice._build_frontmatter`, `capture_collector._build_frontmatter`, `preprocessors/inbox.add_frontmatter`) stay: the writers emit shapes operators and fixtures know (`tags: [voice]` flow style, `raw_transcript: |` block literal, a quoted `origin`) that `frontmatter.serialize` (safe_dump block style) would not reproduce; a write-side fold is a shape decision for a later arc, not a seam fold.
- 2026-10-14 (T03): the slug count was an undercount too — besides the four collector copies, `collectors/health._slug_account` (fallback `"account"`) and two inline `re.sub` slugs in `curiosity/producer.py` carried the same ASCII grammar; folded in T03 (`empty=` keyword). `publish/corpus.server_slug` stays: it is an exact port of context-mcp's `slugifySkillName` (NFKD fold, diacritics stripped) — the SERVER's grammar, pinned as a fixpoint, allow-listed in `tests/test_slugify.py`. A grep for the fence smells (`^---`, `\A---`, `startswith("---`, `find("\n---`) found eight more private frontmatter grammars under functions not named `*frontmatter*` → T07 (seventh task, the slice's maximum).
- 2026-10-14 (reassess after S02): T04 widened to the `basicConfig` inventory S02 found (see the task line). Not in this slice: lazy collector registration (`backlog/lazy-collector-registry.md`, M034) — the `collectors` package imports every module to register it; S03's folds inside collectors (T05, T06) must not add module-level work to that import.
- 2026-10-14 (T04): shipped as one commit instead of the planned A + B — the basicConfig guard
  is red between the halves. `pyproject.toml` untouched (its E402 ignores never named the six
  modules; flush / lint keep theirs for non-logging reasons). The `created:` / `closed:` stamps
  of the S03 artifacts had been estimated up to 80 min ahead of the clock — corrected to the
  commit times of the commits that introduced them.
- 2026-10-15 (T05): the state-writer inventory by mechanism (`.write_text(json.dumps(` on a
  `STATE_DIR` file) was seven, not the audit's three — flush's dedup window, agent-runs, the
  lint cache and the list-shaped `intents-seen.json` (allow-listed: a dict-shaped file with a
  legacy-list tolerance is the producer's shape decision — backlog candidate for M034). The five
  collectors on `load_json_state` / `save_json_state` comply with the seam's written contract
  (atomic, one writer per collector) and stay. Footgun found en route: ruff 0.16 formats the
  Python fences in Markdown by default — `pyproject` now excludes `*.md`; never pipe
  rtk-filtered output into a path variable (an empty `$f` made `ruff format $f` a
  whole-project run).
