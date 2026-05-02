# Architecture Deepening — M003+ Candidates

Surfaced via `/improve-codebase-architecture` walk (2026-05-02), after M002 closed. Four candidates ranked HIGH/MEDIUM. Three explicitly skipped as false positives. Use this file as input to a future `ytstack:plan-milestone`.

Vocabulary: domain terms from `CONTEXT.md`, architecture terms from improve-codebase-architecture's LANGUAGE.md (module / interface / depth / seam / adapter / leverage / locality / deletion-test).

---

## #1 — Scan-Scripts → Collector pattern (HIGH)

**Files:** `scripts/scan-calendar.py` (247), `scripts/scan-browser.py` (524), `scripts/scan-tabs.py` (185), `scripts/scan-screenshots.py` (366). Plus `scripts/flush.py:_LEGACY_PIGGYBACK_COMMANDS` which hardcodes them.

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

## Skipped (false positives, recorded so future walks don't re-suggest)

- **`flush.py` + `flush_pipeline.py` boundary smear.** Re-export-pattern is a polish, not a deepening. Deletion test fails: removing the re-export just moves the import.
- **`prompts.py` (49 lines).** Looks trivial but earns its keep as *a place* — 10 importers means single point of customization. Locality, not depth.
- **`execute-suggestions.py` approval flow.** One client, no seam yet. Deepen when a second approval workflow appears.
- **`utils.py` cohesion split.** Real but LOW-priority polish — three logical groups (state I/O, wiki content, text utils) that don't yet justify a split. Fold into the config-split PR's import-header cleanup or defer.

---

## Suggested milestone framing

**Option M003-A — "Config split + Collectors" (Pattern roll-out).** Slice S01 = #2 (config split, mechanical), S02 = #1 (Collector migration). Sequential because S01 touches every script's import header, S02 touches the same scripts' bodies.

**Option M003-B — "Just config split."** Only #2. Smallest scope, locks the import story before anything else moves. #1 becomes M004.

**Option M003-C — "Just Collectors."** Only #1. Bigger code-reduction win, leaves config-split for later when its motivation gets sharper.

**Option M003-D — "Pre-compile cleanup."** S01 = #2 (config split), S02 = #6 (Preprocessor seam). Hits both shallow-import friction and pre-compile inconsistency in one milestone before touching the Collector epic.

**Option M003-E — "Engine core."** Only #5 (compile.py orchestration). Highest-leverage module gets the cleanest cut. Risky because it touches the engine's hottest path; requires a regression-fixture vault to verify byte-identical wiki output.

Pick at the next `ytstack:plan-milestone` invocation.
