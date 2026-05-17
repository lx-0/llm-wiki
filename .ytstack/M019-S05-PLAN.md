---
milestone: M019
slice: S05
project: llm-wiki
created: 2026-05-17T11:10:00Z
status: done
task_count: 6
completed_tasks: 6
---

# M019-S05 — Slice Plan

**Goal:** Two-pass Analyst-Agent layer fully shipped. Pass-1 reads a single study's deterministic results + relevant substrate, writes `_analysis.md` per run. Pass-2 reads all latest Pass-1 outputs + their `_summary.md` siblings, writes `reports/analyses/<ts>.md` for cross-study synthesis. Pass-2 runs trivially on single-study (wedge) setup; pipeline-symmetry preserved for post-wedge.

## Architecture context

Two-pass architecture locked in DECISIONS.md (`2026-05-17: Reports — two-pass analyst layer ...`). Studies are mechanical/deterministic (M019-S01..S04). Analyst is interpretive and uses real agents via `claude_agent_sdk` with `make_path_scope_gate` from `core.sdk_helpers` (per the 2026-05-17 callback-gate decision, line 802 of DECISIONS).

Persona for wedge: single "operator self-cartography research analyst" persona applied to both passes — broad enough to cover the 5 clinical-screen instruments. Per-study persona pluggability (manifest-pinned) deferred to post-wedge.

## Tasks

- [x] T01 — **`lib/analyst.py` agent-harness.** ✓ Done 2026-05-17. `run_analyst(system_prompt_path, user_prompt, vault_cwd, pass_label, model, max_turns)` wraps `claude_agent_sdk.query` with the exact S01-T01 verified composition (Read/Glob/Grep + disallowed Write/Edit/NotebookEdit + permission_mode default + make_path_scope_gate([]) + prompt_stream). Returns `AnalystResult{markdown_body, elapsed_ms, model_id, persona_version, prompt_version, cost_usd, pass_label}` with persona_version = SHA256[:16] of the persona-prompt file bytes. StderrCapture + log_sdk_failure pattern from compile.py. Empty-body output raises AnalystError (caller doesn't persist half-formed `_analysis.md`).

- [x] T02 — **Persona prompts.** ✓ Done 2026-05-17. `prompts/reports/analyst_per_study.md` (Pass-1 — observer stance, scope-lock, structured output sections: Headline / Cross-instrument synthesis / What changed / What to notice / Open questions; 400-700 word target). `prompts/reports/analyst_cross_study.md` (Pass-2 — integrator stance, no raw substrate re-reads, N=1 honesty section explicit; 250-450 word target at N≥2, 80-150 words at N=1). Both lock the observer-not-clinician framing and require substrate-path citations for every interpretive claim.

- [x] T03 — **Pass-1 CLI + persistence.** ✓ Done 2026-05-17. `wiki analyze --study <id>` (and `--all-studies` default). `_build_pass1_user_prompt()` inlines manifest + per-instrument reports + `_summary.md` + optional previous-run summary for change framing. `_persist_pass1()` writes `<study>/runs/<latest-ts>/_analysis.md` with frontmatter (kind/pass/study_id/run_timestamp/informant_report/persona_version/prompt_version/model_id/cost_usd/elapsed_ms/engine_version). Auto-fires inside `wiki study run` post-success.

- [x] T04 — **Pass-2 CLI + persistence.** ✓ Done 2026-05-17. `wiki analyze --cross-study-only`. `_build_pass2_user_prompt()` inlines each study's manifest + latest `_summary.md` + latest `_analysis.md` (NOT raw substrate). `_persist_pass2()` writes `reports/analyses/<utc-ts>.md` with frontmatter (pass: 2, study_count, persona_version, prompt_version, model_id, cost_usd). N=1 wedge state honestly acknowledged in output (verified live: persona wrote "Only `1` study available in current scope. Cross-study patterns will activate when a second study reports.").

- [x] T05 — **flush.py piggyback orchestration.** ✓ Done 2026-05-17. (a) Pass-1 wired directly into `scripts/study.py:cmd_run` — fires automatically after each successful `wiki study run` (soft-fail: Pass-1 error doesn't undo the run since per-instrument reports are the source of truth). `--no-analyze` flag escapes if operator wants deterministic-only. (b) Pass-2 fires via new `analyst_pass2` piggyback in `_LEGACY_PIGGYBACK_COMMANDS` → `["analyze.py", "--cross-study-only"]`, cooldown 168h (weekly default). Config-knob migration entry shipped (`feedback_config_change_requires_migration`). Default OFF until operator flips `features.operator_reports`.

- [x] T06 — **Live verification + DECISIONS milestone-closeout.** ✓ Done 2026-05-17. Synthetic-study live test (PHQ-9-only baseline against /tmp vault): Pass-1 = $0.0413 / 45.8s / 600-word substrate-grounded analysis citing `raw/notes/voice/2026-05-15-sleep.md` + Oura evidence with correct observer-stance language. Pass-2 = $0.0278 / 21.2s / N=1 honest acknowledgement + lifted Pass-1 framing, no padding. Both outputs have full frontmatter provenance (persona_version, prompt_version, model_id, cost). DECISIONS.md milestone-closeout entry locks 17 architectural decisions across the full wedge (surface location, air-gap, agent capabilities, Bash-escalation defense, scoring determinism, batching strategy, scope ceiling, embedded methodology, future-fit posture, atomic writes, meta-report layer, SVG over matplotlib, two-pass analyst, single overall persona, provider policy, schedule semantics, per-study flock). Cost projection: ~$0.92 per full weekly run, ~$48/year. Wedge exit criteria 1/2/3/5/6/7 ✓; 4 (6 weekly runs) + 8 (operator quote one observation) pending operator dogfooding.

## Done when

- All 6 tasks confirmed.
- One end-to-end live run on lxw with Pass-1 + Pass-2 both producing readable reports.
- Scope-lock proven empirically (agent could not Write).
- DECISIONS.md has milestone-closeout entry.
- All 8 M019-CONTEXT.md exit criteria green.

## Notes

Pass-2 on single-study (wedge state) is intentionally redundant — pipeline-symmetry vs. wedge-discipline trade. Operator picked symmetry (option b) so Migration to N≥2 studies post-wedge is zero-friction.

Persona-pluggability per study (manifest-pinned `persona: clinical-psychology` etc) is deferred to post-wedge. Default = single "operator self-cartography research analyst" persona for both passes. When post-wedge brings personality / values / behavioral-derived studies, the per-study persona-pin landing in study `manifest.yaml` is a small additive change to `lib/analyst.py` — the agent-harness already loads a persona-file path, just needs the lookup-source extended.
