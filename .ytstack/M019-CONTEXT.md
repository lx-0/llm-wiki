---
milestone: M019
project: llm-wiki
created: 2026-05-17T11:04:00Z
size: L
pitch: .ytstack/OFFICE-HOURS-operator-self-reports.md
backlog-stub: .ytstack/backlog/operator-self-reports.md
parallel-with: M018
---

# M019 -- Context

## Goal

Ship the operator-self-reports wedge (c): inference-contract end-to-end with 3-layer scope-lock verified, 5 clinical-screen instruments (PHQ-9 / GAD-7 / ASRS-v1.1 / WHO-5 / MEQ-19) inferred from substrate with embedded methodology, studies manifest + scheduled runs under flock, and a meta-report with graphical change-visualization (cross-instrument radar overlay + coverage-sparkline + per-instrument timeline plots) that activates by run 2.

## Exit criteria

1. **R1 verified** — 3-layer scope-lock probe run with exact `ClaudeAgentOptions` config the inference-agent uses, against a deliberately-engine-targeted Write stimulus. Outcome documented in `.ytstack/KNOWLEDGE.md`. If allowlist held → proceed. If allowlist did not hold → `can_use_tool` callback wired before any inference-run touches real substrate.
2. **R2 verified** — token-budget audit on lxw substrate for the 5 wedge instruments. Headroom for full-scope read documented. Audit method reusable for post-wedge personality instruments.
3. **R3 verified** — `lib/inference.py` implements batched-by-subscale interface from day 1. Wedge instruments run trivially as single-batch (all ≤19 items), but the schema accepts per-subscale batching so personality instruments don't require rework in S05+.
4. **6 weekly study runs** completed against real lxw substrate without intervention failures. Schedule cranked to weekly initially (per Q4-wedge agreement), settles to quarterly afterwards.
5. **Meta-report renders** with: cross-instrument current-state radar (5 axes for 5 wedge instruments, normalized to comparable range); previous-run-overlay radar activating by run 2 for change-visualization; coverage-sparkline (wiki-health-meter); per-instrument timeline plots (score + coverage double-plot).
6. **Embedded methodology** in every report markdown: items + scoring + cutoffs + model-ID + prompt-version + scope-spec + evidence-paths inline. Reports survive deletion of the engine.
7. **Air-gap structurally enforced** — `reports/` excluded from compile.py substrate-scope (hard-coded `disallowed_paths`), not just lint-warned. Recorded in `DECISIONS.md`.
8. **Operator can quote one concrete observation** from the meta-report that they would not have known without it. Subjective test, but the load-bearing demand-signal from Q1.

## Size

L — 4 slices (S01–S04), per the skill rubric. See `M019-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-05-17: Wedge shape = option (c) Two-Runs-Wedge, ~4 slices, 5 clinical-screen instruments. Personality / cleanroom / behavioral-derived instruments deferred to post-wedge (S05+ from backlog stub). Source: Q4 of office-hours pass.
- 2026-05-17: Meta-report (Layer-4 from backlog) is the primary consumption surface; per-instrument reports are infrastructure. Source: Q1 of office-hours pass.
- 2026-05-17: Embedded methodology in every report (items + scoring + model + prompt + evidence inline). Frontmatter-references are insufficient because reports must survive engine deletion. Source: Q6 future-fit posture.
- 2026-05-17: Air-gap from compile-loop is structural, not lint-only. `reports/` excluded from compile.py substrate-scope. Recorded ahead of code in DECISIONS.md.
- 2026-05-17: Inference contract uses Claude SDK only (no Ollama fallback). Curiosity-question generation (when promote-to-curiosity manual escape hatch fires) uses Ollama only. Consistent with existing no-silent-provider-fallback policy.
- 2026-05-17: Inferrer agent batched-by-subscale from day 1 to avoid expensive migration when personality instruments land. Source: eng-review R3.
- 2026-05-17: Radar graphs are core graphical element of meta-report (cross-instrument 5-axis in wedge, per-facet for personality post-wedge). PNG rendering pipeline established in S04 via matplotlib polar plots.

## Open questions

(close as decisions land above)

- **Q1 — `reports/` filesystem location.** Sibling of `knowledge/` at vault root (operator-visible, version-controllable, separate from engine state) vs. under `.wiki/` (engine state, machine-managed). Pitch recommends vault root. Resolve in S01 before any file writes happen.
- **Q2 — PNG rendering invocation.** matplotlib runs in the same process as the engine (heavier import) vs. shells out (slower, isolation). Decide in S04.
- **Q3 — Informant-report framing in report header.** Always-present banner or only in `_summary.md`? Methodological honesty argues always-present. Concrete wording in S04.
- **Q4 — Schedule semantics.** Manifest `schedule: weekly` triggers from flush.py piggyback (existing scheduler) or from a separate cron-style scheduler? Mirror calendar-collector's pattern. Resolve in S03.
- **Q5 — Wedge instruments — exact item-source.** PHQ-9 + GAD-7 + ASRS-v1.1 are PD; items can be transcribed from authoritative sources. MEQ-19 is "free for research" but item-text needs source-cite. WHO-5 PD. Confirm during S01.

## References

- Pitch: `.ytstack/OFFICE-HOURS-operator-self-reports.md` (includes ENG REVIEW annotation with R1/R2/R3 details)
- Backlog stub: `.ytstack/backlog/operator-self-reports.md` (402 lines, full architecture)
- Parallel milestone: M018 (compile.py split) — non-overlapping code paths; can run concurrently across sessions
