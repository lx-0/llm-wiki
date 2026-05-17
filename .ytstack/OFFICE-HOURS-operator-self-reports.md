---
name: operator-self-reports
one-liner: A modular reports/ surface for the llm-wiki operator that runs ~35 validated and cleanroom-derived psychometric instruments as autonomous inference studies against the wiki's substrate, with embedded methodology and a meta-report as the primary consumption surface.
mode: startup
stage: greenfield-feature
date: 2026-05-17
parent-project: llm-wiki
backlog-stub: .ytstack/backlog/operator-self-reports.md
---

# operator-self-reports — Office Hours pitch

**Mode:** Startup (forcing-questions). **Stage:** Greenfield feature within existing llm-wiki project. The architecture was developed iteratively in conversation, captured as `.ytstack/backlog/operator-self-reports.md` (402 lines, committed `31f5316`), then stress-tested via this office-hours pass.

## Why this exists (the deeper layer)

Surface framing: "psychometric instruments running against the operator's substrate."

Deeper framing: the llm-wiki engine produces and accumulates substrate ferociously (5+ collectors live, 30–50 substrate-files/week on lxw), but the consumption surfaces lag. `wiki query` is Pull/ad-hoc, the dashboard is glance-only, curiosity has a published consumer-gap. The engine ingests faster than it returns interpretable value.

Reports are the **first analytical consumption surface** that consumes substrate in a way that no manual or commercial tool can — autonomously, periodically, against validated scientific frames, producing durable self-documenting artifacts. The framing operator chose: *"goldmining on the wiki."*

Critical air-gap: reports never write back into `knowledge/`, `daily/`, `raw/`. Without this, a self-observation-bias feedback loop forms (LLM reads its own report → folds inferred traits into wiki → next inference reads them back → drift compounds). The air-gap is non-negotiable and gets recorded in `DECISIONS.md`.

## Direction

Three architecture layers + one consumption layer:

1. **Instrument plug-in** (`reports/_engine/instruments/<slug>/v<semver>/`) — items.yaml, scoring, cutoffs, render-template, optional substrate-source. ~30 lines of YAML per new instrument.
2. **Study container** (`reports/studies/<id>/`) — manifest declaring (instrument × version × source) tuples, runs/ directory, schedule. Studies are the parallelism unit — fork-from another study + edit manifest = parallel comparison study.
3. **DRY backbone** (`reports/_engine/lib/`) — likert, subscale, cutoffs, inference, provenance, curiosity-bridge, source-adapters, timeline, compare, render, crosscheck.
4. **Meta-report layer** (corrected during Q1 — primary consumption surface, not side-effect) — `studies/<id>/meta.md` with cross-instrument current-state snapshot, change-visualization since last run, coverage-sparkline acting as wiki-health-meter.

Inference is **Informant Report** (LLM-with-substrate-access scoring items), not self-report. Counter-strategy via parallel `source: form` studies that capture self-report; divergence is its own datum.

Conservative confidence default: `min_confidence: 0.75`, `bandable_coverage_pct: 80`. Items below threshold stay unanswered, no auto-curiosity. The wiki grows into the instruments over time; coverage% in the meta-report is the visible measure of that growth.

## Q1 — Demand Reality

Operator's signal: reads periodic self-reports when present, **but only the latest** — and the actually-consumed surface is a meta-report with graphical change-visualization, cross-instrument. Per-instrument reports are infrastructure for the meta-report, not the consumption surface.

This is sharper than "operator wants longitudinal psychometric data." The behavioral evidence is "reads-the-latest-only," which means:

- Build per-instrument-deep-detail at low priority. They serve audit/provenance, not consumption.
- Build meta-report-with-change-vis at high priority. That is the load-bearing artifact.
- Coverage-sparkline-as-wiki-health-meter is consumption-by-glance, requires zero report-reading, and may be the most-consumed artifact of all.

Demand-strength caveat: operator has not yet consumed any periodic self-reporting surface to long-term success (Oura, Headspace, etc., consumed sporadically). Reports could join the consumer-gap unless the meta-report shape is genuinely glance-friendly. This is the main risk — see Risks.

## Q2 — Status Quo

Operator does **nothing** systematically today. This is not a weak-demand signal — clinical assessment path is high-friction and one-shot, DIY across 35 instruments quarterly is infeasible, no commercial tool runs validated psychometrics longitudinally against arbitrary personal substrate. Operator's stated intensity: "HAETTE SEHR SEHR GERNE so ein tracking." Subjective demand explicit.

Q2 anti-pattern ("if nobody does anything, the pain isn't real") doesn't apply here because the tool-cost-to-availability ratio is genuinely prohibitive without an engine like llm-wiki underneath.

## Q3 — Desperate Specificity (skipped)

N=1 operator-as-user. The "actual human" is already named, sitting at the keyboard. Q3's forcing function is not informative for an internal self-cartography surface.

## Q4 — Narrowest Wedge

Operator chose option (c) Two-Runs-Wedge, ~4 slices:

- 5 baseline instruments — PHQ-9, GAD-7, ASRS-v1.1, WHO-5, MEQ-19 (small substrate-scope, simple scoring, fast to ship)
- Inference contract (lib/inference + lib/provenance) end-to-end
- Studies manifest + runs/ layout with flock
- Meta-report layer with current-state snapshot + change-vis + coverage-sparkline
- Schedule cranked initially (weekly first 2 months) so second-run change-vis activates within ~7 days of shipping; settles to quarterly afterwards

Slices S05–S09 from the backlog stub (curiosity-bridge, full 35-instrument catalog, behavioral-derived, cleanroom MMPI, closeout-docs) explicitly **not in wedge**. They follow if-and-when the wedge proves the meta-report shape lands.

Anti-pattern resisted: "all three plus full catalog" was the original lift estimate; the wedge is the schnitt below which the build is abandoned. Operator agreed (c) is the schnitt.

## Q5 — Observation & Surprise (skipped)

No product to observe yet. Defer to post-wedge: first surprise will likely be a divergence between an Informant-Report score and operator's lived sense of that construct. That divergence is the gold the architecture is designed to surface.

## Q6 — Future-Fit

Operator's thesis: **reports are durable self-contained artifacts; the engine is replaceable.** Data outlives code. In 3 years an AI can read these markdown files and reconstruct operator-state-trajectory without needing the engine to run.

This re-shapes one architectural detail with major consequence: **methodology must be embedded in each report**, not referenced. Items, scoring rules, cutoffs, model-ID, prompt-version, scope-spec, evidence-paths all inline in the report markdown (collapsible, but present). A reference like `instrument: phq-9 v1.0.0` in frontmatter is too fragile — `v1.0.0` may not exist in 2029.

Failure-mode b (instrument-version drift breaks longitudinal comparability) is neutralized by embedded-methodology: each historic report self-documents and can be re-interpreted under future psychometric frames.

Failure-mode c (LLM-inference becomes methodologically suspect) is partially mitigated: each report records the model + prompt that produced it, so future audit can adjust historical scores.

Sovereign rationale: same logic as the broader engine — operator's vault carries its own self-contained artifacts; the platform under it is incidental.

## Architecture corrections from this pass

Four amendments to `.ytstack/backlog/operator-self-reports.md` to be captured before plan-milestone:

1. **Layer-4 Meta-Report is primary consumption surface**, not a downstream nice-to-have. Cross-instrument current-state + graphical change-vis. Per-instrument reports are infra.
2. **Wedge is (c) Two-Runs-Wedge** with cranked initial schedule, not the full 9-slice L milestone first. Wedge = ~4 slices, validate consumption pattern, then decide on remainder.
3. **Wiki-Health-Meter (coverage-sparkline)** belongs in the meta-report, not in each per-instrument report.
4. **Embedded methodology in every report** — items, scoring, cutoffs, model-ID, prompt-version, evidence-paths inline. Reports survive engine deletion. Frontmatter references are insufficient.

## Approaches considered

**A) Status quo — defer indefinitely.** Engine continues accumulating substrate; consumption-gap widens. Rejected because operator's explicit demand-signal is high.

**B) Ad-hoc one-shot — `wiki report <slug>` for a single instrument, no studies, no meta-report.** Smallest possible build. Rejected because operator's load-bearing demand is the meta-report and change-vis, not single-instrument-scoring.

**C) Full 9-slice L milestone — entire backlog stub at once.** Rejected per Q4: too much surface area before consumption pattern is validated. Slices 5–9 deferred.

**D) Wedge (c) — 4 slices, 5 instruments, meta-report, change-vis after run 2.** Selected. Validates the consumption shape that office-hours surfaced as load-bearing.

## Recommended approach

Wedge (c), with the following gating:

- After wedge ships and operator has 4–8 weekly runs (~2 months), reassess: is the meta-report being consumed? Is the change-vis providing value? If yes → unlock S05–S09 (curiosity-bridge, full catalog, behavioral-derived, cleanroom, closeout). If no → the consumer-gap pattern reasserted; stop and re-think before more build.
- Cleanroom-MMPI-v0.1 stays in backlog as side-quest, not in wedge.
- Embedded-methodology rule is non-negotiable from S01 — easier to enforce from the start than retrofit.
- Air-gap is non-negotiable from S01 — recorded in DECISIONS.md before any code lands.

## Open questions

1. **Where does `reports/` sit in the vault?** Sibling of `knowledge/` at vault root? Or under `.wiki/` (engine-state)? Recommendation: vault root (operator-visible, version-controllable in operator's git, separate from engine code). Resolve in plan-milestone.
2. **Meta-report rendering — markdown only, or markdown + PNG charts?** Per existing skills/excalidraw-diagram pattern, PNG rendering from in-repo Python. Matplotlib for sparklines + change-vis line plots is the obvious path. Decide in S04.
3. **Is "informant report" framing made explicit to the operator on every report header?** Probably yes — methodological honesty + future-AI-readers benefit. Concrete wording in S04.
4. **Re-run cadence and schedule semantics.** Manifest `schedule: weekly` triggers from flush.py piggyback or from a separate scheduler? Mirror calendar-collector's pattern. Decide in S03.
5. **First cleanroom-instrument-construction workflow.** Side-quest after wedge; not in wedge scope but worth a thinking-pass on item-generation methodology before S05.

## Success criteria

The wedge succeeds if, 2 months post-ship:

- Operator has run ≥6 study runs (weekly for 2 months) without intervention failures
- Meta-report renders correctly with change-vis active by run 2
- Operator can quote a single concrete observation from the meta-report that they would not have known without it
- Coverage-sparkline shows monotonic-or-near-monotonic growth, confirming the "wiki grows into the instruments" thesis is measurable

The wedge fails if:

- Operator stops opening the meta-report after the novelty wears off (consumer-gap pattern repeats)
- Change-vis surfaces noise dominated by LLM-inference variance rather than substrate change
- Confidence-0.75-threshold leaves coverage so low that no instrument reaches bandable after 2 months — implies instruments need more aggressive substrate-scope or lower threshold

## Lift estimate

Wedge (4 slices, ~3 weeks):

- S01 — Engine skeleton + first instrument (PHQ-9) inferred end-to-end + air-gap + embedded-methodology pattern
- S02 — Inference contract (lib/inference + lib/provenance + 3-layer scope-lock) + 4 additional instruments
- S03 — Study manifest + runs/ layout + flock + schedule piggyback
- S04 — Meta-report layer + change-vis + coverage-sparkline + PNG rendering

Post-wedge (only if consumption pattern validated): S05–S09 from backlog stub, ~2 weeks additional.

Cleanroom MMPI-v0.1 side-quest: ~2 weeks separately, not in critical path.

## Risks (carried over from backlog + amended)

1. **Consumer-gap pattern repeats.** Operator stops consuming after novelty. Mitigation: meta-report is glance-friendly (sparkline + 1-paragraph change-summary, not 35 expandable trees); coverage-sparkline delivers value without report-opening; weekly-initial-cadence ensures change-vis activates fast enough to demonstrate the value-prop before novelty fades.
2. **Inference bias.** LLM systematically over-/under-calls; informant-vs-self divergence not yet measurable in wedge (only inferred runs). Mitigation: post-wedge, add `source: both` for 1–2 clinical screens.
3. **Air-gap leak.** Future code accidentally reads `reports/` into compile-loop. Mitigation: hard rule in DECISIONS.md, `AGENTS.md`, lint check that warns if any prompt-file references `reports/`.
4. **Embedded-methodology breaks DRY.** Same scoring rules duplicated into every PHQ-9 report. Mitigation: this is the intended trade — durability over DRY. Generation is automated (rendered from instrument-yaml), so source-of-truth stays single; durability lives in the output, not the input.
5. **Cleanroom legal/methodological misstep.** Documented in backlog; out of wedge scope; revisited post-wedge.

## The Assignment

Next step is `ytstack:plan-ceo-review --mode concept` to stress-test premise and scope before any scaffolding. Plan-ceo-review specifically checks: have we expanded scope where we should have, held scope where we should have, reduced where we should have. Given the wedge correction (full L milestone → 4-slice wedge), plan-ceo-review will likely either reinforce the wedge or push back if it senses the wedge under-scoped a load-bearing capability.

Optional follow-up: `ytstack:plan-eng-review --mode concept` for feasibility check on the inference-contract + 3-layer-scope-lock pattern + embedded-methodology rendering.

After concept-mode reviews land, `ytstack:plan-milestone` to commit the wedge as M### with M-context + M-roadmap, then slice-milestone → spawn-milestone-team (or sequential plan-task).
