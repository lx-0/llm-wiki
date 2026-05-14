# Architecture Deepening — M003+ Candidates

Surfaced via `/improve-codebase-architecture` walk (2026-05-02), after M002 closed. Four candidates ranked HIGH/MEDIUM. Three explicitly skipped as false positives. Use this file as input to a future `ytstack:plan-milestone`.

Vocabulary: domain terms from `CONTEXT.md`, architecture terms from improve-codebase-architecture's LANGUAGE.md (module / interface / depth / seam / adapter / leverage / locality / deletion-test).

---

## #1 — Scan-Scripts → Collector pattern (HIGH — Phase 2 in progress)

**Status update (2026-05-14):** Phase 1 (relocation) complete. Phase 2 (Protocol migration) underway — **scan-tabs + scan-calendar ported.** Both are now Registry-discoverable (`@register` + `SPEC`), run via `wiki collect tabs` / `wiki collect calendar`, retain direct-CLI invocation. Same-class re-registration is a no-op in `base.py:register` to handle `__main__ ↔ collectors.<name>` double-load. 16 unit tests across the two (Protocol conformance + dry-run + write-path + holiday-filter + collision detection). Convention locked: migrated collectors get snake_case filenames (`scan_tabs.py`, `scan_calendar.py`); unmigrated keep the hyphen.

**Remaining Phase-2 ports:** browser (524 LOC, multi-source), screenshots (366 LOC, vision-LLM sub-step), youtube (>700 LOC, tier system + CLI flags). The screenshots and youtube ports will likely surface Protocol gaps (e.g. flag pass-through for tier/limit/backfill) — extension via `SPEC.cli_args` is a candidate.

**Files (Phase 2 scope):** `scripts/collectors/scan-calendar.py` (247), `scripts/collectors/scan-browser.py` (524), `scripts/collectors/scan-tabs.py` (185), `scripts/collectors/scan-screenshots.py` (366), `scripts/collectors/scan-youtube.py`. Plus `scripts/flush.py:_LEGACY_PIGGYBACK_COMMANDS` which hardcodes them.

**Problem:** Four near-clones of the same procedure (read substrate → metadata → `raw/` → log). Each reinvents CLI parsing, state tracking, report formatting. They bypass the `Registry` entirely; `flush.py` carries a legacy hardcoded dispatch table specifically for them. The Collector seam exists and works (EmailCollector proved it during M002) — these scripts are leaving its leverage on the table.

**Shape after deepening:** Each becomes a `Collector` subclass (`scripts/collectors/calendar.py`, `browser.py`, `tabs.py`, `screenshots.py`) with its own `SPEC`. Auto-discovered via `Registry`. Dispatch via `wiki collect <name>`. `flush.py:_LEGACY_PIGGYBACK_COMMANDS` deletes; piggyback discovery is purely registry-driven. Estimated ~40% line reduction across the four (CLI/state/error-handling boilerplate moves to base).

**Out of scope for the migration:** Adapter seams for sub-backends (e.g. Firefox vs. Chrome). Browser is a singleton substrate (per CONTEXT.md "Substrate-with-accounts") — no `Reader`/`Filter` split needed.

**Risks / shape-divergence to watch:**
- Screenshots has a vision-LLM sub-step (different from Email's pure-metadata flow) — does the `Collector` interface accommodate without forcing a fake `is_configured()`?
- Browser does multi-source aggregation (tabs + bookmarks + visits) inside one script — split into multiple Collectors, or one with multi-output?
- Scan-tabs imports browser-tab raw data; possible overlap with scan-browser.

**Verification:** `wiki collect --list` shows email, calendar, browser, tabs, screenshots. `flush.py` cooldown loop spawns each via Collector path, no hardcoded list. Existing piggyback-flush schedule still fires correctly post-migration.

---

## #2 — Config split: `paths.py` + `config.py` (HIGH, design locked)

**Files:** `scripts/config.py` (71 lines, path constants + time helpers + bridge to wiki_config), `scripts/wiki_config.py` (512 lines, CONFIG singleton + dataclasses + validation + round-robin backup). 36 importer sites across `scripts/`, `hooks/`, `wiki` CLI. Eleven scripts import from BOTH.

**Problem:** Two modules, one fuzzy boundary, with circular import (`config.py` imports `wiki_config.CONFIG` for `TIMEZONE`). Caller can't answer "where does this new setting go?" without reading both. Module names don't communicate the actual split.

**Locked design** (decided 2026-05-02 during architecture grill — *not* a minimal-diff merge):

The two modules have different *natures* and deserve to stay split, but with honest names:
- **`scripts/paths.py`** — eager path constants computed from `__file__`. No deps. Pure locality (Path-construction in 20 sites consolidates here).
- **`scripts/config.py`** — `CONFIG` singleton, YAML-driven, lazy-loaded, with validation + round-robin backup. Real module-with-state.
- **`scripts/utils.py`** — gains `now_iso()` and `today_iso()` (currently mis-located in config.py).
- `TIMEZONE` (CONFIG-derived) stays in `config.py`.
- `wiki_config.py` → renamed to `config.py`.
- 36 importer sites migrated mechanically (`from wiki_config import CONFIG` → `from config import CONFIG`; `from config import RAW_DIR` → `from paths import RAW_DIR`).

**Deletion test passes both ways:** removing `paths.py` scatters `Path(__file__).parent.parent` across 20 files; removing `config.py` scatters `yaml.safe_load + dataclass parsing + backup logic` across N callers. Both modules earn their keep at their own seam.

**Verification:** all scripts run; pytest green; `grep -rE "from wiki_config" scripts/` returns empty; no circular imports.

---

## #3 — Model seam (MEDIUM — interface not yet stable)

**Files:** `scripts/ollama_client.py` (160), direct `query()` calls (claude-agent-sdk) and `ollama_client.chat()` calls scattered across `compile.py` (511), `lint.py` (326), `review-wiki.py` (226), `optimize-claude-md.py` (149), `scan-screenshots.py` (366).

**Problem:** Two-LLM architecture (Claude SDK for synthesis, Ollama for classify / curiosity / vision-OCR) with no unifying seam. Temperature defaults, retry logic, schema handling, gotcha-knowledge (`format:json is not enough`, see `.ytstack/KNOWLEDGE.md`) live as copy-paste fragments across five scripts.

**Shape after deepening:** A `scripts/model.py` (or `scripts/adapters/model/`) with `generate_text()`, `generate_structured(schema)`, `generate_vision(image)`. Dispatcher resolves backend from CONFIG or explicit `model_kind=` param. Centralized retry / temperature / schema-validation. Each consumer becomes thinner.

**Why MEDIUM, not HIGH:** Interface still forming. Async-vs-sync gap (Claude SDK is async, ollama_client is sync). Schema-shape diverges (Ollama JSON schema vs. Claude tool-use schema). Vision is Ollama-only today. Two clients aren't a real seam yet — three or four would be.

**Pre-work before this can be a milestone:** decide async-vs-sync (or explicit dual-shape), inventory the schema variants, list every gotcha that should consolidate.

---

## #4 — Linter seam (MEDIUM — shapes diverge more than mailbox)

**Files:** `scripts/lint.py` (326), `scripts/review-wiki.py` (226), `scripts/optimize-claude-md.py` (149).

**Problem:** Three scripts with the same shape: gather input → LLM call → report → output. Each reimplements its own issue-aggregation, its own report-format, its own backup-pattern. Locality of "what does a check look like?" is dispersed.

**Shape after deepening:** A `Linter` `Protocol` with `run() → LintReport`. `LintReport` is a shared dataclass (issues, fixes, metrics). Checks are pluggable. Three scripts become thin CLI wrappers calling the linter with different check factories.

**Why MEDIUM, not HIGH:** lint is structural+semantic, review-wiki is quality-only, optimize-claude-md is mutation-focused. Shapes diverge more than `Reader`/`Filter` did. Could end up forcing a fake unified interface.

**Pre-work:** read all three scripts and decide whether their *outputs* are similar enough that one `LintReport` shape works, or whether the seam fights back.

---

## #5 — `compile.py` orchestration vs. I/O separation (HIGH)

**Files:** `scripts/compile.py` (511 lines).

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

## Skipped (false positives, recorded so future walks don't re-suggest)

- **`flush.py` + `flush_pipeline.py` boundary smear.** Re-export-pattern is a polish, not a deepening. Deletion test fails: removing the re-export just moves the import.
- **`prompts.py` (49 lines).** Looks trivial but earns its keep as *a place* — 10 importers means single point of customization. Locality, not depth.
- **`execute-suggestions.py` approval flow.** One client, no seam yet. Deepen when a second approval workflow appears.
- **`utils.py` cohesion split.** Real but LOW-priority polish — three logical groups (state I/O, wiki content, text utils) that don't yet justify a split. Fold into the config-split PR's import-header cleanup or defer.
- **CLI dispatch (`wiki` bash → Python argparse).** Today only `wiki collect` delegates to a Python dispatcher (`cli_collect.py`). One delegating subcommand isn't a seam. Revisit when 3+ subcommands need shared dispatch (post Backlog #1 + #6).
- **Environment-variable schema.** Only 2-3 env-var lookups exist (`CLAUDE_INVOKED_BY` recursion guard, `IMAP_*_USER/PASS` for mail). Pattern hasn't emerged yet. Defer until a third use case lands.
- **Test coverage as a standalone backlog item.** ~700 test lines for ~6300 code lines is a *symptom* of the deepening opportunities above (untestable interfaces), not a separate item. Coverage rises naturally as #1, #5, #6, etc. land — each refactor's RED-GREEN-REFACTOR cycle adds tests for the new shape. Backfilling tests against tangled legacy interfaces is busywork that locks the bad shape in place.

---

## Suggested milestone framing

**Option M003-A — "Config split + Collectors" (Pattern roll-out).** Slice S01 = #2 (config split, mechanical), S02 = #1 (Collector migration). Sequential because S01 touches every script's import header, S02 touches the same scripts' bodies.

**Option M003-B — "Just config split."** Only #2. Smallest scope, locks the import story before anything else moves. #1 becomes M004.

**Option M003-C — "Just Collectors."** Only #1. Bigger code-reduction win, leaves config-split for later when its motivation gets sharper.

**Option M003-D — "Pre-compile cleanup."** S01 = #2 (config split), S02 = #6 (Preprocessor seam). Hits both shallow-import friction and pre-compile inconsistency in one milestone before touching the Collector epic.

**Option M003-E — "Engine core."** Only #5 (compile.py orchestration). Highest-leverage module gets the cleanest cut. Risky because it touches the engine's hottest path; requires a regression-fixture vault to verify byte-identical wiki output.

**Option M003-F — "Hygiene pass."** S01 = #13 (datetime helpers, prevent latent tz-bugs), S02 = #9 (logging config consolidation), S03 = #11 (markdown helper). Three cross-cutting MEDIUMs that each shrink the surface area for future bugs without touching core engine logic. Low-risk foundation milestone before engine refactors.

Pick at the next `ytstack:plan-milestone` invocation.
