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

## Skipped (false positives, recorded so future walks don't re-suggest)

- **`flush.py` + `flush_pipeline.py` boundary smear.** Re-export-pattern is a polish, not a deepening. Deletion test fails: removing the re-export just moves the import.
- **`prompts.py` (49 lines).** Looks trivial but earns its keep as *a place* — 10 importers means single point of customization. Locality, not depth.
- **`execute-suggestions.py` approval flow.** One client, no seam yet. Deepen when a second approval workflow appears.

---

## Suggested milestone framing

**Option M003-A — "Pattern roll-out".** Slice S01 = #2 (config split, mechanical), S02 = #1 (collector migration). Skip #3 / #4 entirely; they're not ripe. Sequential because S01 touches every script's import header, S02 touches the same scripts' bodies.

**Option M003-B — "Just config split".** Only #2. Smallest scope, locks the import story before anything else moves. #1 becomes M004.

**Option M003-C — "Just collectors".** Only #1. Bigger code-reduction win, leaves config-split for later when its motivation gets sharper.

Pick at the next `ytstack:plan-milestone` invocation.
