# 0.3.0 architecture-deepening arc — followups

Deferred items reported by the 14 candidates (C01–C14) of the 0.3.0 arc (commits `4678f0c`…`eba4644`, 2026-07-18 → 2026-07-22). Grouped by candidate; cross-cutting items collected at the top. Reconciled backlog statuses live in `architecture-deepening.md` (Refresh summary 2026-07-22).

## Cross-cutting

- **Repo-wide ruff baseline is NOT clean and never was** — every candidate independently confirmed ~160–220 pre-existing findings (F401/F541/E702/E402 across scripts/, tests/, docs build scripts; identical sets on main). Ruff is deliberately absent from `.pre-commit-config.yaml` and never lints `.ts`. A dedicated lint-sweep candidate + a `[tool.ruff.lint]` select/ignore policy in pyproject.toml would make `ruff check .` a meaningful gate. Individual stragglers named by candidates: `core/utils.py:25` F401 `LOG_FILE`; `compile.py` F401s (json/logging/LOG_FILE/STATE_FILE/render/ollama_client + local `Compile`); `config.py:1174` F402; runner.py/inference.py/audit_scope.py/render_summary.py (reports); health_trends.py E402 ×2 + tests/test_health_trends.py; desktop eslint 9 warnings (8 no-non-null-assertion, 1 unused `CONF_COLOR` in src/triage.ts renderer).
- **Stale baseline test counts in briefs:** the arc's waves grew the suite 1422+1 → ~1716+1; later stages must not diff against 1422.

## C12 — Preprocessor seam

- ~~Integration: expose `wiki preprocess` in the `wiki` bash + menu~~ — done in the same wave (commit `3b595f5`).
- ~~docs/engine-layout.md:112 still lists `scripts/clippings_sweep.py` as the sweep home~~ — fixed in the 0.3.0 docs pass.
- `docs/architecture.excalidraw:8020` caption names clippings_sweep.py — still accurate (shim exists); left untouched due to the excalidraw render-review gate. Could mention the preprocessor seam in a future diagram pass.
- Optional consolidation: `scan_youtube.py` keeps its own local `slugify(text, max_len=60)`; now that `core.utils.slugify` has `max_len` it could fall to core.utils too.

## C09 — Collector harness

- Migrate calendar's per-calendar watermark (`calendar_collector.py` ~line 872, `newest_updated`) onto the `Watermark` helper — same advance-on-max contract, but nested per-calendar inside `_run_one_account`; left as-is to avoid touching the state-shape the calendar tests assert on.
- jamie + gmeet still call `daily_capture.append` directly for the meetings rollup (not via the shared `append_rollup`) — they are account collectors, not the inbox trio. A future pass could route them through `base.append_rollup` for a single swallowed-failure rollup path.
- M027 Q6/S06: decide FolderIndexCollector auto-scheduling. Registered with `piggyback_default=False` (visibility only); when Q6 resolves system-scheduler-vs-piggyback, flip the default and add a `piggybacks.folder-index` knob (+ config migration) if piggyback is chosen.
- email_collector deliberately NOT on `run_account_loop` (bespoke two-mode loop + decision-locked state shape + structured per-account failure recording). If full uniformity is ever wanted, `run_account_loop` needs an optional inline-failure-handler mode; today that is over-engineering for one caller.

## C10 — Reports interface sweep

- **Behavior change to watch:** retryability unification now retries two malformed-output variants ("agent output is not a JSON object", "missing/invalid items object") that were previously non-retryable purely by omission. Strictly safer (same 3-attempt cap), but a real behavior change.
- Per-instrument `scope:` blocks (wider substrate for personality instruments) remain the documented post-wedge extension point in `substrate_scope.py` — not implemented.
- `wiki analyze`'s docstring/help still advertises `--all-studies` / `--pass2-only` / `--cross-study` flags the argparser never defined (pre-existing; only `--cross-study-only` exists).

## C13 — Compile dead-ladder deletion

- `docs/PROCESS.md:298-300` (German) still describes the deleted `compile_large_source_chars` 50KB auto-upgrade escalation and references `compile_large_source_model` as a size-threshold fallback — needs a doc-sync pass (`sync-process-docs`) to reflect that the only model escalation is the kind=unknown retry.
- `compile_stages/classify.py:classify(content, source)` no longer uses `source` after removing the instructions branch; kept for interface stability. A future signature-tightening could drop it.

## C07 — Desktop seam (part A) + part B

- ~~Engine-side `--json` for the scraped surfaces~~ — shipped as C07 part B (commit `cc08130`).
- `compile.py`'s dedup/review/curiosity phases have no structured progress mode; desktop `compile.ts` keeps the human `[i/total]` regexes for those three. Extend `--progress-json` if their GUI progress ever matters.
- No prose fallback for older engines by design (app ships with the engine) — if the desktop app is ever distributed separately, version-gate the JSON seams.

## C08 — Daily flock + markers (and markers-adoption wave)

- `daily_digest_runner._inject_captures_section` is a HEADING-delimited section replace, not a begin/end sentinel pair — deliberately left OUT of core.markers. If a heading-section primitive is ever wanted, add `markers.replace_heading_section` (distinct contract) rather than overloading the sentinel primitive.
- ~~calendar_collector + web_research sentinel splices~~ — migrated onto core.markers in the arc's final wave (commit `ca6fe5f`).

## C11 — Dream deepening

- OFF-LIMITS-at-the-time `wiki` bash help: drop the phantom `--cost-cap` line (wiki:413), the `limits.dream_entity_max_cost_usd` reference (wiki:419-420), and the "per-run cumulative cost caps are enforced" note (wiki:446) — the flag crashes argparse and the knob was removed per the 2026-05-23 no-dollar-caps decision. (Verify against the post-C06 dispatcher help before editing — the heredocs moved.)
- Optional: consolidate the 3 near-identical dream vault fixtures (test_dream_cycle/sampling/priority) into one shared helper. Polish, not a blocker.
- Sweep/piggyback CLI exit codes changed 5 → per-kind 3/4/6. If any external monitoring keyed on exit 5, switch to per-kind (or nonzero-means-failed).

## C06 — CLI dispatcher

- ~~AGENTS.md one-line note that scripts/cli.py's CommandSpec table is the catalog source of truth~~ — done in the 0.3.0 docs pass.
- dream + dream-entity keep their per-command `--help` as bash heredocs (bespoke sweep-alias argv routing); their top-level `wiki help` entries ARE table-sourced. Could migrate later for full single-sourcing.
- refresh-after commands (compile/lint/correct/dedup/take) import flush.py (loads claude_agent_sdk) in the dispatcher process to reach the locked refresh — small SDK-import tail. If it ever matters, extract flush.py's locked refresh into a light module (flush.py was pinned import-only this arc).

## C03 — Frontmatter grammar

- `desktop/src/vault/triage.ts` `field()` strips surrounding quotes but does not unescape YAML single-quote doubling (`''` → `'`) in summaries; cosmetic only — align with the new writer when the desktop is next touched.
- Remaining ~15 opportunistic frontmatter parse sites stay on private grammars until touched: `dream.py:189`, `core/prompts.py:39`, `core/agent_spec.py:107` (should adopt `frontmatter.parse_strict`), `pin.py:50`, `collectors/gmeet.py:209`, `health_trends.py:56-66`, `migrations/migrate_add_type.py:49`, hooks, dashboard.

## C01 — SDK harness (M021 S01)

- Remaining hand-rolled `async for … in query()` sites for later M021 slices: `suggestions/producer.py`, `facts/takes_producer.py`, `curiosity/backends/folder_providers.py`, `producers/intents.py`, `flush.py`, `lint.py`, `optimize-claude-md.py` (+ the deliberate hand-built probes `probe_compile_scope.py`, `reports/_engine/verify_scope_lock.py`).
- M021 S02 (Ollama side): `core/ollama_client.py` sync-in-async + asyncio.to_thread bridge — still open.
- `.ytstack/M021-ROADMAP.md` scoping is stale ("7+ call sites" vs 24 files) and M021 `status:planned` should flip to in-progress/S01-done.
- Behavior sharpening to review: `agent_task.py` now exits 2 on a structured is_error ResultMessage (previously silently wrote output + returned 0 after e.g. error_max_turns); `inference.py` surfaces a clean-exit is_error as its classified kind instead of mislabeling empty output as retryable schema_invalid.
- `query.py` keeps `state['total_cost']` (dashboards read `total_cost_lifetime`) but now accumulates SDK-reported actuals; extending the 2026-05-23 no-dollar decision to removing the state key + dashboard stat is a separate operator decision.
- Latent dual-module duality: reports lib imports `scripts.core.*` while engine scripts import `core.*` — under pytest both module instances exist with separate LEDGER objects. Tests patch the shared object's record method (works either way), but consolidating the sys.path juggling in reports/_engine would remove the trap.

## C05 — Config schema

- `scripts/collectors/scan_screenshots.py:552` docstring still says `_LEGACY_PIGGYBACK_COMMANDS` (collectors tree was off-limits to C05) — one-line docstring fix when that tree is open.
- Wizard model list is still hardcoded in `lib/config.sh` (only the downgrade bug was fixed); the fuller idea — wizard reads model choices from the Python side — remains open. Any future compile-model default bump must update the select_one list + case arms, or the catch-all downgrade class returns.
- `docs/cli.md:374` still says "grouped tables" about docs/config.md — tables are now flat per-section; cosmetic.
- Consider exposing the docs generator via the dispatcher (`wiki config docs --write`?).

## C04 — Lint corpus seam

- **Operator re-baseline on lxw** (mandated by `orphan-check-footer-masking.md`): after `wiki update`, run `wiki lint --structural-only` and review the newly surfaced orphan batch BEFORE treating the dashboard Orphans queue as actionable — footer unmasking jumps the count from ~0 to a real number. Verified in a scratch vault, not on lxw.
- Operator vault `dashboard.md` needs the template resync (missing-backlinks queue row removed in templates/dashboard.md): until `wiki seed`/vault-patch propagates, the live DataviewJS queue loop references a `missing_backlinks_count` frontmatter key that `_dashboard-lint.md` no longer writes.
- `docs/PROCESS.md:292` still references removed `core.utils.count_inbound_links`; PROCESS's Lint-triage section still describes 4 queues incl. check_missing_backlinks; `docs/cli.md` lint blurb describes the pre-C04 check list — for the next `sync-process-docs` pass.
- `.ytstack/backlog/orphan-check-footer-masking.md` is implemented (footer-aware fix + oracle retirement shipped; re-baseline pending operator) — mark/close it there.
- `dashboard_stats --dry-run` intentionally does NOT persist the lint-results cache (dry-run writes nothing).

## C02 — StateStore

- `scripts/reports/_engine/study.py:363` still hand-rolls the NB try-lock (excluded from the brief's migration list) and its docstring cites the now-removed `compile._acquire_exclusive_lock` name — migrate onto core.state_store primitives in a later pass.
- `core/daily_capture.py` markdown-append flocks (off-limits this wave) could reuse `core.state_store.locked` once its owner allows.
- Collector-private watermark savers write non-atomically (`email_collector.py:486`, `folder_index.py:309` raw write_text) — low stakes (torn write = re-scan, not money); route through save_json_state opportunistically.

## C14 — Exception seam

- Out-of-scope remaining unlogged shapes (mechanical pass = silent-pass + bare-return only): 3 bare-continues (`adapters/mailbox/thunderbird.py:~248/296`) and ~11 unlogged fallback-assignments (e.g. `dedup.py:719`, `core/config.py:90`, `preprocessors/inbox.py:76`, `collectors/_picture_metadata.py:146`, `dashboard/lint_results.py:74`) could adopt the labeled swallow() form in a later sweep.
- `desktop/` (TypeScript) has its own catch-swallow census — untouched; needs its own seam if wanted.
- `health.py` probe-failure WARNINGs now also reach stderr when build_health runs inside the interactive home-screen banner; if that gets noisy, route the banner's build_health call through a handler filter (failure is abnormal, so likely fine).
