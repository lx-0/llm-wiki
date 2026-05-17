---
milestone: M019
slice: S05
project: llm-wiki
created: 2026-05-17T11:10:00Z
status: planned
task_count: 6
completed_tasks: 0
---

# M019-S05 — Slice Plan

**Goal:** Two-pass Analyst-Agent layer fully shipped. Pass-1 reads a single study's deterministic results + relevant substrate, writes `_analysis.md` per run. Pass-2 reads all latest Pass-1 outputs + their `_summary.md` siblings, writes `reports/analyses/<ts>.md` for cross-study synthesis. Pass-2 runs trivially on single-study (wedge) setup; pipeline-symmetry preserved for post-wedge.

## Architecture context

Two-pass architecture locked in DECISIONS.md (`2026-05-17: Reports — two-pass analyst layer ...`). Studies are mechanical/deterministic (M019-S01..S04). Analyst is interpretive and uses real agents via `claude_agent_sdk` with `make_path_scope_gate` from `core.sdk_helpers` (per the 2026-05-17 callback-gate decision, line 802 of DECISIONS).

Persona for wedge: single "operator self-cartography research analyst" persona applied to both passes — broad enough to cover the 5 clinical-screen instruments. Per-study persona pluggability (manifest-pinned) deferred to post-wedge.

## Tasks

- [ ] T01 — **`lib/analyst.py` agent-harness infrastructure.** Wrapper around `claude_agent_sdk.ClaudeSDKClient` with: `make_path_scope_gate(['reports/', 'knowledge/', 'daily/', 'raw/'])` for Read+Grep access (no Write/Edit); `prompt_stream(...)` per the 2026-05-17 constraints; `disallowed_tools=[Write, Edit, NotebookEdit]`; `permission_mode != 'acceptEdits'`; `setting_sources=["project"]`; `StderrCapture` + `classify_failure` per existing pattern. Loads persona from `prompts/reports/analyst_<pass>.md`. Returns `AnalystResult{markdown_body: str, evidence_paths: list[str], elapsed_ms: int, model_id: str, persona_version: str, prompt_version: str}`. Unit-tests with mock SDK client: gate denies Write-attempts; allows Read of `reports/` + `knowledge/`; returns structured result on happy path; surfaces classified failure on SDK error.

- [ ] T02 — **Persona prompts in `prompts/reports/`.** Two files: `analyst_per_study.md` (Pass-1 system prompt, focused on within-study reading: "Read the per-instrument reports + _summary.md for one study run, identify within-study patterns + caveats + open questions, cite substrate-paths for any specific claims") + `analyst_cross_study.md` (Pass-2 system prompt: "Read all latest per-study _analysis.md outputs + their _summary.md siblings, synthesize cross-study patterns + convergent/divergent signals; if only one study is available, acknowledge N=1 and produce a thinner synthesis honestly"). Both personas require embedded-provenance output: every interpretive claim cites the source path. Informant-report framing in the system prompt (this is observer-analysis, not self-report). Version-hash via filename SHA256 captured in `AnalystResult.persona_version`.

- [ ] T03 — **Pass-1 end-to-end + persistence:** `wiki analyze --study <id>` CLI subcommand. Resolves the study's latest run directory, loads all per-instrument `.md` files + `_summary.md`, builds Pass-1 prompt with these contents inline + scope-resolver pointing the agent at relevant substrate (`raw/notes/voice/`, `daily/`, etc. — depends on which instruments and their lookback windows). Invokes `lib/analyst.py` Pass-1. Persists output to `reports/studies/<id>/runs/<ts>/_analysis.md` atomic-rename (mirror S03 pattern), with frontmatter (`pass: 1`, `study_id`, `run_ts`, `persona_version`, `prompt_version`, `model_id`, `evidence_paths`). Embedded methodology block inline (persona text + Read-tool transcript + cited substrate paths). Verification: live-run on lxw `longitudinal-baseline` produces a readable, self-contained `_analysis.md` after T03 + S01..S04 are landed.

- [ ] T04 — **Pass-2 end-to-end + persistence:** `wiki analyze --cross-study` CLI subcommand. Globs `reports/studies/*/runs/<latest-ts>/_analysis.md` + their `_summary.md` siblings, builds Pass-2 prompt with all of them inline. Invokes `lib/analyst.py` Pass-2. Persists output to `reports/analyses/<ts>.md` (NOT under any single study — this is cross-study) with frontmatter (`pass: 2`, `studies_synthesized: list`, `persona_version`, `prompt_version`, `model_id`, `evidence_paths`). On single-study wedge state: persona honestly acknowledges N=1 and produces a thinner synthesis ("only longitudinal-baseline available in current scope; cross-study patterns will activate when a second study reports"). Verification: live-run after T03 produces `reports/analyses/2026-05-XX.md` with N=1 caveat present in output body.

- [ ] T05 — **flush.py piggyback orchestration.** After every `wiki study run`, automatically trigger `wiki analyze --study <id>` for that study (Pass-1 happens per-study-run, no extra schedule needed). Pass-2 runs on its own schedule (config key `personal.reports.cross_study_schedule: str = "weekly"`, default), checked by `flush.py` piggyback alongside compile/study-due-checks. Config-key migration entry in same commit (`feedback_config_change_requires_migration` memory). Verification: `wiki study run longitudinal-baseline` on lxw fires Pass-1 automatically; Pass-2 fires next time `wiki flush` runs and the cross-study schedule is due.

- [ ] T06 — **Live test on lxw + scope-lock verification + DECISIONS milestone-closeout.** End-to-end run: `wiki study run longitudinal-baseline` produces 5 deterministic instrument reports + `_summary.md` (S01..S04 work). Pass-1 piggybacks automatically, produces `_analysis.md`. Manual `wiki analyze --cross-study` produces `reports/analyses/<ts>.md`. Verify: (a) both analyst outputs have embedded methodology + provenance + cited substrate paths; (b) `make_path_scope_gate` denied any Write/Edit attempt from the agent during either pass (check StderrCapture log for blocked-call events, or absence of unexpected file modifications); (c) the 8 M019 exit criteria from M019-CONTEXT.md all confirmed. DECISIONS.md milestone-closeout entry summarizing what M019 locked architecturally.

## Done when

- All 6 tasks confirmed.
- One end-to-end live run on lxw with Pass-1 + Pass-2 both producing readable reports.
- Scope-lock proven empirically (agent could not Write).
- DECISIONS.md has milestone-closeout entry.
- All 8 M019-CONTEXT.md exit criteria green.

## Notes

Pass-2 on single-study (wedge state) is intentionally redundant — pipeline-symmetry vs. wedge-discipline trade. Operator picked symmetry (option b) so Migration to N≥2 studies post-wedge is zero-friction.

Persona-pluggability per study (manifest-pinned `persona: clinical-psychology` etc) is deferred to post-wedge. Default = single "operator self-cartography research analyst" persona for both passes. When post-wedge brings personality / values / behavioral-derived studies, the per-study persona-pin landing in study `manifest.yaml` is a small additive change to `lib/analyst.py` — the agent-harness already loads a persona-file path, just needs the lookup-source extended.
