---
milestone: M031
project: llm-wiki
size: L
created: 2026-08-25T15:30:00Z
status: done
total_slices: 4
completed_slices: 4
---

# M031 Roadmap (Reliability Wave)

**Goal:** Audit-found defects fixed at class level: flush + retry queue, index drift, link grammar + S-fixes, doctor freshness gates.

**Exit criteria:** see M031-CONTEXT.md (7 items, all live-verified on lxw).

## Slices

- [x] S01 -- DONE 2026-08-26: root cause was host-MCP schema injection — the CLI merged the host's MCP server tools into every request and one ships a schema the API rejects (top-level oneOf/allOf/anyOf → 400 → exit 1, empty stderr). Fix: `--strict-mcp-config` + `mcp_servers={}` on every engine SDK call, incl. flush.py which bypasses the harness. Three hypotheses were refuted first (size-class, stale session env — my "causal proof" there was confounded and the comments were corrected to "hygiene, not fix" — and ANSI escapes). **Live queue 234 → 0.** Tail note: the last stubborn contexts were transient, not a new class (one re-probed clean in 6.1 s); the true straggler was `flush-context.md`, stranded since 2026-07-25 because `pending()` silently dropped names `parse_name` rejected — fixed (`ef965d7`) and drained.
- [x] S02 -- Index drift DONE 2026-08-26: root cause was the LLM prompt step itself (told to upsert a table it must not read) — replaced by the deterministic `core/index_sync.py` post-compile pass + `wiki reindex` CLI; prompt step removed. Live: 362 deduped / 33 dropped / 574 appended, control dry-run 2024 rows · 0 changes · idempotent (== corpus). Drift gate folded into S04's doctor checks (one home). Expected one-time follow-on: ~574 publish updates (better descriptions) on the next piggyback fire.
- [x] S03 -- DONE 2026-08-26: bash-`[[…]]` wikilink guard; lint mixed-str/int-tag crash fix; piggyback stale-last_error overwrite; dollar-counter retirement in `_persist_outcome`; gmeet export dead-letter (negative cache + 7d re-probe); compile_model knob (E3). Commits d9f167b/e0b4b63/2560580/9d49fbe/431bc7d/8e6f2dc; suite 1881 green; live on lxw.
  **Three of these were wrong or partial and were corrected the same day in 0.5.1 — see the re-audit note under S04.** (a) The wikilink guard reached only `WIKILINK_RE`'s own consumers; `lint`/`links_audit`/route use a second grammar copy, so the live errors it was written for survived. (b) `compile_model` was NOT a dead knob — five agentic surfaces read it, and the Haiku flip downgraded `wiki correct apply`. (c) "nothing reads `total_cost`" was false (four readers, one rendering to the operator's dashboard). Also corrected: the E4 refutation recorded here ("9 keys = deliberate NEVER_INJECTED") **collapses** — the never-inject premise is measurably false, 7 keys were moved to INJECTED_KEYS; and the two gmeet knobs landed in the WRONG table, so they never reached the vault at all. E10 (scan_youtube self-cap) stands.
- [x] S04 -- DONE 2026-08-26: `wiki doctor` gained `piggyback-health` (failed/timeout outcome, run stuck past the wall-clock cap, substrate dark) + `index-drift` (dry-run reconciler, dispatchable `wiki reindex` fix) — the two checks the audit's own fix-direction named. Both live-verified on lxw, and the live run immediately exposed two bugs in the check itself (wrong state keys → 12 healthy tasks reported never-run; short cadences flagged dark after 12 quiet hours) — fixed with a scheduler-derived task list and a staleness floor. CHANGELOG 0.5.0 + version + lock; both infographics folded to steady state (architecture advertised a `wiki health` command that does not exist → `wiki doctor` + `wiki reindex`); all three canvas gates run, gate 3 caught a pill overflow the bbox+glyph scans passed.

**Re-audit (post-S04, same day):** an adversarial 4-dimension pass over this milestone's own commits returned 24 confirmed findings — 3 in code shipped hours earlier (compile_model downgrade, half-reaching links guard, half-retired dollar counter) and 7 misfiled config knobs that reach no operator vault. All fixed and released as 0.5.1; lessons in `KNOWLEDGE.md` + `CLAUDE.md`.

## Run order

Sequential; `ytstack:reassess-roadmap` at each slice boundary.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all summarize-confirmed; update `completed_slices`; on completion flip `status`.
