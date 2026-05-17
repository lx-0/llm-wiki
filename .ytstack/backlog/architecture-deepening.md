# Architecture Deepening — M003+ Candidates

Surfaced via `/improve-codebase-architecture` walk (2026-05-02), after M002 closed. **Refreshed 2026-05-17** after the codebase ~2×'d in size (compile.py 511→1340, dream.py 0→1091, lint.py 326→1214, new subpackages facts/, suggestions/, curiosity/, dashboard/, sessions/, and new collectors pictures/voice/gmeet/jamie/health/calendar).

Vocabulary: domain terms from `CONTEXT.md`, architecture terms from improve-codebase-architecture's LANGUAGE.md (module / interface / depth / seam / adapter / leverage / locality / deletion-test).

## Refresh summary (2026-05-17)

- **2 fully resolved:** #1 Scan→Collector, #2 Config split.
- **1 partially resolved:** #4 Linter seam — lint.py absorbed the LLM-contradiction phase internally. Defer until a 3rd semantic-check shape appears.
- **9 unchanged carry-forwards:** #3, #5–#13 from the original walk (priorities held).
- **4 new:** #14 Producer seam, #15 Dashboard consolidation, #16 dream.py phase extraction, #17 rename `_LEGACY_PIGGYBACK_COMMANDS`.
- **1 graduated MEDIUM → HIGH:** #3 Model seam (was 2 LLM call sites in 2026-05-02 → 7+ today).
- **Active design grilled out:** **#14 (Producer seam) + #5 (compile.py orchestration)** were grilled into a two-milestone arc; design lives in `.ytstack/backlog/producer-seam.md`. Pick up there at next `ytstack:plan-milestone`.

---

## #1 — Scan-Scripts → Collector pattern (✅ DONE — Phase 2 complete 2026-05-14)

**Resolved 2026-05-14.** All five `scan-*.py` scanners ported to the Collector Protocol. `wiki collect --list` now shows seven Registry collectors: `email`, `jamie`, `tabs`, `calendar`, `browser`, `screenshots`, `youtube`. `_LEGACY_PIGGYBACK_COMMANDS` carries zero substrate collectors — only `lint_structural`, `review_wiki`, `optimize_claude_md`, `retry_failed_flushes`, `curiosity_followup` (non-substrate tasks, legacy by design). 44 unit tests across the five new collectors.

Migration log (commits): `5362f6c` tabs (pilot) · `1b0a2d3` calendar · `b60c4cc` browser · `9d41c68` screenshots + config-key migration · scan-youtube (this commit).

Notable findings during the ports:
- **Convention locked:** migrated collectors get snake_case filenames (`scan_tabs.py` etc.) — hyphenated names aren't importable as Python modules. `base.py:register` made idempotent for same-class re-registration (handles the `__main__ ↔ collectors.<name>` double-load when a collector module is run directly).
- **browser** stayed ONE collector (not split per-browser) — singleton substrate, no Reader/Filter seam. Surfaced + fixed a pre-existing latent bug: `scan_stg` / `scan_firefox_places` used `.exists()` guards that pass for empty-config `Path()` == cwd.
- **screenshots** was the only scanner in `_LEGACY_PIGGYBACK_COMMANDS`. Porting moved it to Registry-discovered piggyback (`piggyback_default=True`). Config key `scan_screenshots` → `screenshots`; `scripts/migrations/migrate_config_keys.py` shipped to migrate operator config.yaml (also `follow_requests`→`curiosity_followup`, drops removed `sync_memories`).
- **youtube** — the feared "Protocol gap" did NOT materialise into a `SPEC.cli_args` extension. Resolution: the Collector `run()` is the **inbox-drain mode** (processes `raw/inbox/youtube.md`); the rich per-URL flags (`--url`/`--tier`/`--no-skip`) stay CLI-only — same split already established by calendar's `--year` and browser's `--source`. The orchestration loop was extracted into a shared `_ingest_items()` helper used by both `main()` (CLI) and `drain_inbox()` (Collector). No Protocol change needed.

**Pattern that emerged for all five ports:** the scan functions were already pure (`scan_backup`, `scan_calendar`, `generate_report`, …) — the port is a thin `@register class XCollector` wrapper with `SPEC` + `is_configured()` + `run()`, plus a result-dict return value where the legacy `scan()` returned `None`. CLI-only flags stay on `main()`; the Collector path does the piggyback-shaped full-sweep / inbox-drain behaviour.

---

## #2 — Config split: `paths.py` + `config.py` (✅ DONE 2026-05-14)

**Resolved 2026-05-14.** The fuzzy `config.py` / `wiki_config.py` boundary is gone. Three honestly-named modules under `scripts/core/`:
- **`core/paths.py`** (NEW) — eager path constants from `__file__`. Zero deps, zero side effects. The dependency-free base of the config layer.
- **`core/config.py`** (was `wiki_config.py`) — `CONFIG` singleton, YAML-driven, validation + round-robin backup + get/set/keys CLI. Now also owns the `.env` bootstrap (`load_dotenv` at import) and `TIMEZONE` (CONFIG-derived). Imports `CONFIG_FILE` / `DOTENV_FILE` from `paths.py`.
- **`core/utils.py`** — gained `now_iso()` / `today_iso()` (no config dependency → they belonged here, not in the stateful config module).

The old circular import (`config.py` ↔ `wiki_config.py` for `TIMEZONE`) is eliminated: import DAG is now `paths` (leaf) → `config` / `utils` → everything else.

**Migration mechanics:** 37 importer sites swept by a one-shot Python rewriter (`/tmp/sweep_config_imports.py`) that buckets each imported symbol → `paths` / `config` / `utils` and emits up to three import lines. Mixed imports like `from core.config import RAW_DIR, TIMEZONE, now_iso` became three lines. A follow-up merge pass deduplicated same-module import lines. `scripts/migrations/*.py` were swept too (they're importer sites). No config.yaml *data* migration needed — the split is import-path only, the YAML schema is unchanged.

**Verification:** 204 pytest green; `grep -rE "wiki_config" scripts/ hooks/` returns empty; `python -c "from core import paths, config, utils"` clean; bash -n + gitleaks pass; all CLIs + `wiki collect --list` smoke-test clean. Commit: this one.

**Test-side fallout fixed:** `test_correct.py` (`monkeypatch.setattr(config, "FACTS_DIR")` → path consts moved to `paths`; patch the consumer modules `correct`/`utils` instead), `test_s02_adapters.py` + `test_config_backup.py` (`from core import wiki_config` → `config`), `test_s03_gmail.py` (indented `from core.config import STATE_DIR` → `paths`).

---

## #3 — Model seam (HIGH — graduated from MEDIUM 2026-05-17)

**Files:** `core/sdk_helpers.py` (258), `core/ollama_client.py` (160); 7+ LLM call sites today: `compile.py`, `curiosity/producer.py`, `suggestions/producer.py`, `facts/takes_producer.py`, `review-wiki.py`, `ingest-html.py`, `scan_screenshots.py`, `scan_youtube.py`, `pictures.py`, `voice.py`.

**Problem:** Two-LLM architecture (Claude SDK async for synthesis, Ollama sync for classify / curiosity / vision-OCR) with no unifying seam. Temperature defaults, retry logic, schema handling, gotcha-knowledge (Ollama `format:json` insufficient, schema variants, vision-OCR quirks — all in `.ytstack/KNOWLEDGE.md`) live as copy-paste fragments. `core/sdk_helpers.py` addresses **one side** (Claude SDK error classification + stderr capture); the other side (Ollama wrapping, schema unification, async-sync bridging) is still scattered.

**Shape after deepening:** A `scripts/llm.py` (or `scripts/adapters/llm/`) with `generate_text(prompt, model=None, temperature=None, timeout=None)`, `generate_structured(prompt, schema, model=None)`, `generate_vision(image_path, prompt, model=None)`. Dispatcher resolves backend from CONFIG or explicit `model_kind=` hint. Centralized retry + cost estimation + failure classification. Wraps Ollama with `asyncio.to_thread()` so the async/sync mismatch stops blocking the event loop in curiosity calls.

**Why HIGH (graduated 2026-05-17):** Old walk said "two clients aren't a real seam yet — three or four would be." Now there are 7+. Threshold crossed. Couples to old #10 (async/sync boundary), which is subsumed by this seam.

**Sequencing:** If sequenced **after** the Producer seam (`.ytstack/backlog/producer-seam.md`), the Model seam swaps into a single Producer-orchestrator wrapper instead of touching all three producer bodies + compile.py + 4 collectors. Strong case for ordering Producer-seam → compile-orchestration → Model-seam.

**Pre-work:** inventory schema variants (Claude tool-use vs. Ollama JSON-schema vs. Ollama structured-output), enumerate every gotcha in KNOWLEDGE.md that should consolidate, decide single async interface (recommend yes — wrap Ollama via `asyncio.to_thread()`).

---

## #4 — Linter seam (PARTIALLY RESOLVED — defer 2026-05-17)

**Status:** lint.py grew 326 → 1214 LOC and absorbed the LLM-contradiction phase internally (guarded by `--structural-only`). One of the three "gather → LLM → report" clients moved inside lint.py rather than reaching for a shared seam. The remaining two (`review-wiki.py` 226, `optimize-claude-md.py` 163) are now 2 adapters = hypothetical seam.

Lint.py now has its own shallow-interface problem (two linters in a trench coat, leaky `--structural-only` flag), but that's a within-file refactor, not a seam.

**Defer until:** a third semantic-check shape appears (e.g. a schema-compliance lint, a citation-validation lint). Then reopen with three real adapters.

---

## #5 — `compile.py` orchestration vs. I/O separation (HIGH — got WORSE since 2026-05-02)

**Status (2026-05-17):** Grilled into a design doc at `.ytstack/backlog/producer-seam.md` as **Milestone-B** of the two-milestone arc (Producer seam first, then this).

**Files:** `scripts/compile.py` — **1340 LOC** (was 511; ~2.6× growth).

**Problem:** Three phases (select source files → extract via LLM → commit wiki article) plus two post-passes (curiosity loop, suggestion generation) live in one tangled loop. File I/O is woven *inside* the LLM-orchestration; retrying a failed extraction without re-reading source, batching extractions across many files, or testing extraction without file-ops all require surgical cuts into the function. Lines 463–486 already show the post-passes spawning as separate async tasks — but they're triggered from the same loop with implicit state-threading.

**Shape after deepening:** A `Compiler` module (or three free functions if Protocol overhead isn't worth it) with three pure stages:
- `select(criteria) → list[Path]` — pure I/O, no LLM.
- `extract(content: str) → WikiArticle` — pure LLM, no file ops.
- `commit(article: WikiArticle, path: Path)` — pure I/O, no LLM.

`compile.py` becomes a thin orchestrator: `for f in select(): commit(extract(f.read()), output_path)`. Curiosity + suggestion passes become post-processors keyed off the result list, not entangled in the per-file loop.

**Why HIGH:** Deletion test: remove this seam and you scatter state-threading + LLM-retry-policy + file-op coupling across N callers. Locality argument is strong (the engine's central function is currently un-testable end-to-end without mocking five layers).

**Pre-work / risks:**
- The classification pass (which subdirectory does this file go into?) interleaves with extraction — does it stay in `extract` or become its own stage?
- Cost-tracking is currently threaded through the loop; needs a clean exit point in the stage refactor.
- Curiosity/suggestion passes are async; the orchestrator boundary needs to handle "fire-and-forget post-passes" without losing exit codes.

**Verification:** existing pytest suite green. `wiki compile --dry-run` produces the same file list it did before. End-to-end compile of a fixture vault produces byte-identical wiki articles (regression check).

---

## #6 — Preprocessor seam (HIGH)

**Files:** `scripts/process-inbox.py` (252), `scripts/ingest-html.py` (283), `scripts/clippings_sweep.py` (102).

**Problem:** Three scripts that *prepare* files for the compile loop (inbox-routing, HTML→Markdown, Obsidian-clippings sweep). They share shape (read source → transform → write to `raw/`) but have no common interface. Naming inconsistent (`sweep` vs. `ingest` vs. `process`); CLI / dry-run / logging boilerplate reimplemented per script. They are *not* Collectors — they don't read a Substrate, they normalize already-collected raw material before compile reads it.

**Shape after deepening:** A `Preprocessor` `Protocol` parallel to `Collector` (`scripts/preprocessors/base.py`):
- `SPEC` ClassVar (name, output_subfolder, default_enabled)
- `run(dry_run: bool) → PreprocessResult`
- Auto-discovery via Registry (same pattern as Collectors)
- `wiki preprocess <name>` subcommand
- Optional: chain into compile loop's pre-step (so `wiki compile` triggers preprocessors first)

**Why HIGH:** Three scripts with structurally identical work, no seam between them today. Cheaper than the Collector epic because no Reader/Filter sub-split needed (preprocessors are singletons, not account-substrates).

**Naming concern:** `Preprocessor` and `Collector` need to stay distinct. Suggest `CONTEXT.md` gets a Preprocessor entry pinpointing the difference — Collectors read from outside the vault (mailbox, calendar, browser), Preprocessors normalize what's already inside the vault's `raw/` or `inbox/`.

**Verification:** `wiki preprocess --list` shows three names. Each runs the same way the legacy script did. `flush.py` piggyback path can dispatch them via Registry (same shape as Collectors).

---

## #7 — Hook-dispatch harness (MEDIUM)

**Files:** `hooks/session-end.py` (119), `hooks/pre-compact.py` (112), `hooks/session-start.py` (81), `hooks/_transcript.py`.

**Problem:** `session-end` and `pre-compact` are ~95% identical: stdin → JSON-parse → Windows-backslash workaround → `read_transcript()` → flush_pipeline staging → spawn `flush.py`. The only deltas are `MIN_TURNS_TO_FLUSH` and the `kind` parameter. `session-start` is read-only and diverges (no flush staging, only context injection). Backslash-regex fix is duplicated; if hook input schema changes, two files must update.

**Shape after deepening:** `hooks/_harness.py` with:
- `read_hook_input()` — centralized stdin + JSON-parse + backslash-normalization.
- `run_session_flush(input, kind: str, min_turns: int)` — shared flush-staging path.
- `run_context_inject(input)` — separate path for session-start.

Each hook script becomes a 10-line wrapper.

**Why MEDIUM, not HIGH:** session-start diverges enough that the abstraction doesn't have three uniform clients yet — it has 2.5. Two adapters is a hypothetical seam (per LANGUAGE.md); three is real. Worth doing once any new hook (post-compact? pre-tool?) lands and forces the count to 3+.

**Verification:** all three hooks fire end-to-end in a real Claude Code session; transcripts get staged, context gets injected; no regressions in flush behavior.

---

## #8 — `StateStore` module + concurrency safety (MEDIUM, with race-risk angle)

**Files:** `scripts/utils.py:load_json_state` / `save_json_state` (8 lines), consumed by `scripts/compile.py`, `scripts/query.py`, and indirectly `scripts/retry-failed-flushes.py` via `flush_pipeline`. State files in `state/`: `state.json`, `email-state.json`, `screenshot-state.json`, dedup windows, cooldowns.

**Problem:** "Load JSON → mutate → save" pattern reimplemented across 3+ scripts. State schema implicit (no type hints, no documentation). **Race-risk:** piggybacks can spawn multiple scripts in parallel via `flush.py`; two scripts simultaneously mutating `state.json` lose writes (last-writer-wins). No atomic-rename, no file-lock today.

**Shape after deepening:** A `StateStore` module (e.g. `scripts/state.py`) with:
- Typed schema (TypedDict or dataclass) for each known state file.
- `load(path) → State`, `save(path, state)` with atomic-rename (`tmp + os.replace`).
- `increment_field(path, key, delta)` — atomic read-modify-write under file lock (`fcntl.flock` on POSIX).

Each script imports one StateStore per state-file-kind; schema is documented at the StateStore.

**Why MEDIUM (not HIGH):** today's usage is simple enough that the abstraction can feel like over-engineering. *But* the race condition is real — it's a latent bug that becomes a HIGH the moment two piggybacks fire concurrently and corrupt state. Worth keeping on the radar; promote to HIGH if a state-corruption incident lands in `KNOWLEDGE.md`.

**Pre-work:** audit current state-file writers, list every concurrent-write path through `flush.py` piggyback dispatch, decide whether file-locking is the right shape vs. a single-writer queue.

**Verification:** existing tests green; new test `tests/test_state_store_concurrent.py` spawning two writers + asserting no lost increments.

---

## #9 — Logging configuration + structured fields (MEDIUM)

**Files:** `scripts/lint.py` (326), `scripts/review-wiki.py` (226), `scripts/optimize-claude-md.py` (149). Plus scattered `logging.basicConfig()` calls in scan-* and compile.py.

**Problem:** Three distinct logging-format strings across the linter trio (`[%(levelname)s] %(name)s: %(message)s` vs. `%(asctime)s  %(levelname)s  %(message)s` vs. raw markdown writes to `KNOWLEDGE_DIR / "log.md"` in `optimize-claude-md.py`). Mix of `log.info()`, `log.exception()`, `print()` for final output. No structured fields (request-id, async-task-id, module). If we ever want OTLP-shipping, log-level filtering, or correlation IDs, we touch every script.

**Shape after deepening:** A `scripts/logging.py` module with `configure_logger(name: str, log_file: Path | None = None, structured: bool = False) → Logger`. Standard format. Optional structured-JSON output. All scripts call it on import. Deletion test passes: today, "add a correlation-id field" requires editing N scripts; with the seam, one line.

**Why MEDIUM:** the friction is real but cheap-to-fix individually; the real value lands when *any* observability requirement arrives (currently none). Worth doing alongside the Linter-seam (Backlog #4) — both consolidate the same three scripts.

**Verification:** all scripts emit the same format; `tests/test_logging_config.py` asserts structured mode produces parseable JSON.

---

## #10 — Async / sync LLM boundary in `compile.py` (MEDIUM, latent hotspot)

**Files:** `scripts/compile.py` (511), `scripts/ollama_client.py` (160).

**Problem:** `compile.py` has four `async def` functions (`compile_file`, `maybe_generate_suggestions`, `maybe_generate_curiosity_requests`, `main`) that internally call **sync** `ollama_client.chat()` and `query()` (Claude SDK is async; ollama_client is sync `httpx` calls). The `async` shape buys concurrency *between* files; per-file LLM calls block the event loop. At scale (100+ raw files in one compile run, especially on the curiosity / suggestion post-passes that fan out further), one slow Ollama response stalls the batch.

**Shape after deepening:** Either:
- `scripts/async_ollama.py` wrapping `ollama_client.chat()` via `asyncio.to_thread()` for thread-pool offload, OR
- A true async HTTP client inside `ollama_client` (e.g., `httpx.AsyncClient`).

Then suggestion + curiosity passes use `asyncio.gather()` for fan-out instead of serial awaits.

**Why MEDIUM:** only one consumer today (`compile.py`), so technically not a real seam yet (one adapter = hypothetical seam). But it's a latent hotspot — the moment compile-throughput becomes a problem, the refactor is forced. **Couples to Backlog #3 (Model seam):** if we build the Model seam, build it async-first from day 1 instead of paying the conversion later.

**Verification:** benchmark `wiki compile` on a fixture vault with 50+ files; assert post-deepening wall-time drops by N% with concurrent LLM calls.

---

## #11 — Markdown rendering helper (MEDIUM)

**Files:** `scripts/scan-calendar.py`, `scripts/scan-browser.py`, `scripts/scan-tabs.py`, `scripts/scan-screenshots.py`, `scripts/lint.py`, `scripts/review-wiki.py`, `scripts/optimize-claude-md.py`. Plus `scripts/collectors/email.py:_render_report`.

**Problem:** ~7 scripts hand-assemble Markdown reports: `lines = [f"# Title — {today_iso()}", "", "| Col | Col |", "|---|---|", *rows]; output_path.write_text("\n".join(lines))`. Frontmatter assembly, table generation, code-fence formatting, list wrapping — each script does its own thing. There's no shared "write a report with title + table + sections" helper.

**Shape after deepening:** `scripts/markdown.py` with:
- `Report` dataclass (`title`, `frontmatter: dict`, `sections: list[Section]`)
- `Section` dataclass (`heading`, optional `paragraphs: list[str]`, optional `table: Table`, optional `bullets: list[str]`)
- `Table` dataclass (`headers`, `rows`)
- `render_report(report) → str` — handles frontmatter YAML, GFM tables, escape-pipe-in-cells, indent-blocks for nested bullets

**Why MEDIUM:** the abstraction is real (7 callers) but each caller's needs are ~80% overlapping, ~20% custom. Risk of forcing a fake unified shape. Pre-work: read all 7 report-rendering paths, list which features each needs, decide if the union covers them or if a `RawSection(content: str)` escape-hatch is needed.

**Coupling:** if Backlog #1 (scan → Collector) lands first, the migration into Collector subclasses is the natural moment to swap in the markdown helper. Bundle accordingly.

**Verification:** new tests render `Report` fixtures to expected strings; existing scan-* output matches byte-identical (or close, modulo whitespace) post-migration.

---

## #12 — Exception-handling pattern consistency (MEDIUM)

**Files:** ~51 `except Exception:` / `except BaseException:` blocks across `scripts/compile.py`, `scripts/ollama_client.py`, `scripts/scan-calendar.py`, `scripts/scan-browser.py`, `scripts/scan-screenshots.py`, `scripts/lint.py`, `scripts/review-wiki.py`, `scripts/optimize-claude-md.py`, and others.

**Problem:** Four distinct patterns coexist with no documented intent:
1. Catch + `log.exception()` + `return None` (graceful-agnostic intent)
2. Catch + `log.exception()` + `continue` (swallow + resume next iteration)
3. Catch + `pass` (silent swallow — debugging nightmare)
4. Catch + `log.exception()` + fall-through (probably-unintended; control flow ambiguous)

Silent swallows hide root-cause information; inconsistent recovery semantics make it hard to know whether a script "succeeded with caveats" vs. "failed silently."

**Shape after deepening:** A small `scripts/errors.py` with:
- `swallow(name: str)` — context-manager that logs the exception with name + classification (transient / fatal) and re-raises iff classified fatal.
- `Result[T]` lightweight wrapper (`Ok(value)` / `Err(error)`) for functions that should never throw to caller.

Replace all 51 sites with explicit choice: `with swallow("classify_email"): ...` or `result = try_classify(); if isinstance(result, Err): ...`. Pattern becomes greppable and reviewable.

**Why MEDIUM:** the inconsistency is real, but a 51-site refactor is touch-heavy and most sites are correct-as-is. Best done incrementally during other deepenings (touch a script for a different reason → also normalize its exception handling). Could become a HIGH if a silent-swallow incident lands in `KNOWLEDGE.md`.

**Coupling:** belongs in the same PR as Backlog #5 (compile orchestration) — that refactor will already touch `compile.py`'s exception sites.

---

## #13 — Datetime / timezone consistency (MEDIUM, latent tz-bugs)

**Files:** `scripts/scan-calendar.py`, `scripts/scan-browser.py`, `scripts/scan-screenshots.py`, `scripts/health.py`, `scripts/optimize-claude-md.py`. Plus the recently-fixed `scripts/adapters/mailbox/thunderbird.py:_parse_date`.

**Problem:** Mixed datetime intent across scripts:
- `datetime.now()` (naive local, no tz) — `health.py`, `optimize-claude-md.py`
- `datetime.now().strftime("%Y-%m-%dT%H%M")` (local slug, ambiguous) — `scan-screenshots.py`
- `today_iso()` from `config.py` (tz-aware, UTC) — `compile.py`, `lint.py`, scan adapters
- `datetime.utcnow()` (naive UTC, deprecated in Python 3.12) — random places

The M002-finalize tz-aware fix (normalize all incoming dates to UTC in `thunderbird.py:_parse_date`) didn't propagate to these scripts. Latent bugs: comparing naive-local vs. tz-aware datetimes raises `TypeError`; comparing two naive-but-different-meaning datetimes silently returns wrong order.

**Shape after deepening:** A `scripts/time.py` (or fold into `scripts/utils.py`) with:
- `utc_now() → datetime` — tz-aware UTC, the default for all metadata / state / comparisons.
- `local_now() → datetime` — tz-aware *local* (uses `CONFIG.scheduling.timezone`). For user-facing output only (filenames, log timestamps).
- `parse_to_utc(raw: str) → datetime | None` — generalize `thunderbird.py:_parse_date`'s normalization.
- `slugify_ts(dt: datetime) → str` — single canonical filename slug.

Audit all `datetime.*` callsites and migrate. Intent becomes explicit at the type level.

**Why MEDIUM (close to HIGH):** any single tz-mix bug in production manifests as a hard crash (the offset-naive-vs-aware `TypeError`) or worse, silently-wrong sort order. Easy to write, hard to detect. Already cost us one debug round in M002-finalize.

**Verification:** `tests/test_time_helpers.py` asserts tz-aware return types; grep `datetime.now()\|datetime.utcnow()` in scripts/ returns 0 matches post-migration.

---

## #14 — Producer seam (HIGH — NEW 2026-05-17)

**Status:** Grilled into a design doc at `.ytstack/backlog/producer-seam.md` as **Milestone-A** of the two-milestone arc (this seam first, then `compile.py` orchestration from #5). CONTEXT.md updated with Producer / ProducerSpec / ProducerResult / ProducerRegistry vocab in the same arc.

**Files:** `scripts/suggestions/producer.py` (83), `scripts/curiosity/producer.py` (348), `scripts/facts/takes_producer.py` (230); call site `scripts/compile.py:1272-1281`.

**Problem:** Three independent post-compile modules with identical async shape (`async def maybe_X(source: Path) -> None`). Cost guards, retry logic, error classification, gate checks all duplicated. Returns `None` — orchestrator can't aggregate results. **Latent bug:** any producer raising silently skips the per-file state save (state save at line 1288 is *after* all three awaits), so the next compile run re-spends Claude SDK tokens.

Three different gate-shapes today: suggestions has zero CONFIG gate + hardcoded `_is_email_source()` filter; curiosity has `features.curiosity_loop` only; takes has `features.extract_takes` + `limits.extract_takes_source_globs`.

**Shape after deepening:** `ProducerSpec` Protocol + `ProducerRegistry` parallel to `CollectorSpec`/`Registry`. `ProducerResult` dataclass replaces `None` return. Two declarative gates on Spec (`enabled_config_key`, `source_glob_config_key`), both evaluated by the orchestrator — eliminates in-method gate code. Failure-contract α: orchestrator wraps + logs, never blocks state-save.

**Deletion test:** Passes — cost guards, retry policy, error classification, and the state-save bug all reappear if the seam is removed.

**Subsumes:** `.ytstack/backlog/preflight-guard-rollout.md` (the missing `assert_prompt_within_budget` calls land naturally in the orchestrator wrapper).

---

## #15 — Dashboard suite consolidation (MEDIUM — NEW 2026-05-17)

**Files:** `scripts/dashboard/dashboard_stats.py` (327), `scripts/dashboard/dashboard_lint.py` (206), `scripts/dashboard/inject_daily_button.py` (112), `scripts/dashboard/agent_buttons.py` (185).

**Problem:** Four scripts independently read, mutate, and write the YAML dashboard file. Each has its own state-loading + merging. No shared "update dashboard section" helper.

**Shape after deepening:** `scripts/dashboard/base.py` with `DashboardSection(title, content, metadata)`, `load_dashboard()`, `update_section(dashboard, section_name, content)`, `save_dashboard()` with atomic-replace + frontmatter preservation. Each script becomes thin: compute → `update_section()` → save.

**Deletion test:** Passes — YAML mutation logic scatters across 4 scripts if removed.

**Coupling:** Same pattern as #6 (Markdown rendering helper). If both land in one milestone, the dashboard cache files and the markdown reports can share the same renderer for tables.

---

## #16 — `dream.py` phase extraction (MEDIUM — NEW 2026-05-17)

**Files:** `scripts/dream.py` (1091).

**Problem:** Five internal phases (entity resolution, corpus collection, prompt assembly, SDK call, orchestration) are clear in code but not in the public interface. Corpus collection + cost estimation are deterministic but can't be unit-tested without mocking the SDK call. Orchestration logic (cooldown, cost caps) is mixed with loop control.

**Shape after deepening:** Extract three top-level functions: `resolve_entity(slug)`, `collect_dream_corpus(entity)` (encapsulates collection + tiering), `estimate_dream_cost(corpus)`. Keep `dream_entity()` and `dream_all_entities()` as orchestrator entry points; they call the extracted helpers.

**Why MEDIUM (not HIGH):** Deletion test is marginal — the phases become inline if removed; the coupling doesn't vanish, just becomes less visible. The payoff is testability + future dashboard reach-widget reuse. No API consumer exists yet.

**Defer until:** dashboard or API work needs entity-reach metrics, OR cost-estimation grows complex enough to merit isolation.

---

## #17 — Rename `_LEGACY_PIGGYBACK_COMMANDS` (LOW — NEW 2026-05-17 — 5-min polish)

**Files:** `scripts/flush.py:78-97`.

**Problem:** Misnomer. The dict contains `dream_cycle` (M014, brand-new) alongside legacy tasks. Name suggests "to-be-deleted" but the list is a permanent fixture alongside Registry-discovered Collectors.

**Solution:** Rename to `_BUILTIN_PIGGYBACK_TASKS`. No logic change. Clarifies intent for future maintainers — and prepares for an eventual world where the Producer seam discovers more piggyback tasks via Registry, leaving this dict as the irreducible non-Collector / non-Producer remainder.

**Deletion test:** N/A — pure naming polish.

---

## Skipped (false positives, recorded so future walks don't re-suggest)

- **`flush.py` + `flush_pipeline.py` boundary smear.** Re-export-pattern is a polish, not a deepening. Deletion test fails: removing the re-export just moves the import.
- **`prompts.py` (49 lines).** Looks trivial but earns its keep as *a place* — 10 importers means single point of customization. Locality, not depth.
- **`execute-suggestions.py` approval flow.** One client, no seam yet. Deepen when a second approval workflow appears.
- **`utils.py` cohesion split.** Real but LOW-priority polish — three logical groups (state I/O, wiki content, text utils) that don't yet justify a split. Fold into the config-split PR's import-header cleanup or defer.
- **CLI dispatch (`wiki` bash → Python argparse).** Today only `wiki collect` delegates to a Python dispatcher (`cli_collect.py`). One delegating subcommand isn't a seam. Revisit when 3+ subcommands need shared dispatch (post Backlog #1 + #6).
- **Environment-variable schema.** Only 2-3 env-var lookups exist (`CLAUDE_INVOKED_BY` recursion guard, `IMAP_*_USER/PASS` for mail). Pattern hasn't emerged yet. Defer until a third use case lands.
- **Test coverage as a standalone backlog item.** ~700 test lines for ~6300 code lines is a *symptom* of the deepening opportunities above (untestable interfaces), not a separate item. Coverage rises naturally as #1, #5, #6, etc. land — each refactor's RED-GREEN-REFACTOR cycle adds tests for the new shape. Backfilling tests against tangled legacy interfaces is busywork that locks the bad shape in place.

---

## Suggested milestone framing (refreshed 2026-05-17)

The 2026-05-02 M003 options (now historical — see git for the original list) are obsolete: #1 + #2 shipped, #4 partially resolved. New framings against the current backlog:

**Option Engine-Core arc — "Producer seam + compile.py + Model seam."** Three milestones in sequence, fully grilled in `.ytstack/backlog/producer-seam.md`:
- M-A: #14 Producer seam (4 slices)
- M-B: #5 compile.py orchestration (6 slices)
- M-C: #3 Model seam (graduated to HIGH, ready when M-A+B settled)

Highest leverage, biggest regression surface. Recommended path.

**Option Hygiene pass — "Cross-cutting MEDIUMs."** S01 = #13 (datetime/tz helpers), S02 = #10 (logging config), S03 = #6 (Markdown helper). Three cross-cutting MEDIUMs that each shrink the surface area for future bugs without touching the engine's hot path. Low-risk foundation milestone before engine refactors.

**Option Dashboard-and-render — "Output-layer consolidation."** S01 = #15 (Dashboard suite), S02 = #6 (Markdown helper). Two output-side renderers consolidating onto shared rendering primitives. Independent of engine refactors; safe to interleave.

**Option Pre-compile cleanup — "Preprocessor seam."** Only #11 (process-inbox / ingest-html / clippings_sweep). Single-milestone Preprocessor Protocol parallel to Collector. CONTEXT.md gets a Preprocessor entry. Cheaper than the Producer seam (singleton scripts, no Reader/Filter sub-split).

**Option Quick-win — "Rename + dream extraction."** S01 = #17 (rename `_LEGACY_PIGGYBACK_COMMANDS`, 5-min), S02 = #16 (dream.py helper extraction, ~1 day). Two cheap polishes. Useful filler between engine milestones.

Pick at the next `ytstack:plan-milestone` invocation. Operator already steered toward Engine-Core arc on 2026-05-17 (grilled #14+#5 into `.ytstack/backlog/producer-seam.md`).
