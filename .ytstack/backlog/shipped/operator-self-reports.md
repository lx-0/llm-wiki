# Operator self-reports — modular parallel psychometric studies

A `reports/` surface running ~35 validated and cleanroom-derived psychometric instruments as **inference studies** against the operator's substrate. Each instrument is a self-contained plug-in. Each study is an independent manifest of (instrument × version × source). Studies run autonomously, in parallel, and accumulate longitudinal runs so the operator can watch the wiki grow into the instruments over time.

This is the engine's first **read-only analytical surface**: reports never write into `knowledge/`, `daily/`, `raw/`. Hard air-gap from the compile-loop. Without this air-gap a self-observation-bias feedback loop forms (LLM reads its own report → folds inferred traits into wiki → next inference reads them back → drift compounds). Non-negotiable.

## One-liner

> "Modular parallel psychometric studies that infer scores from your substrate; reports grow more complete as the wiki grows."

## The gap it fills

Today the wiki captures *what* you did, said, met, slept. There is no surface that **integrates** that data through validated psychometric frames. Operator currently has zero longitudinal psychometric data on themselves and no obvious path to acquire it — clinical instruments are usually one-shot questionnaires done in distress, not quarterly observations against an accumulating record.

This is the **self-cartography-engine's natural extension**: same substrate, different lens. The wiki already knows enough about an operator to infer most of a PHQ-9 or HEXACO honestly; what's missing is the engine.

## Methodological framing

This is **Informant Report**, not Self Report. Crucial distinction:

- **Self-report bias eliminated** — depression-self-criticism distortion, narcissistic grandiosity, social desirability all bypassed. The observer doesn't share the operator's distortions.
- **New bias class introduced** — LLM may over- or under-call symptoms based on substrate-distribution (many voice-notes about sleep problems → PSQI overcalled; few mentions of joy → WHO-5 undercalled).
- **Counter-strategy** — parallel `source: form` study with the same instrument captures self-report; divergence becomes its own datum. Architecture supports this trivially (two manifest entries with different `source:` fields).
- **Some instruments have published Informant versions** (PID-5-IRF, ASRS-Informant, BFI-Informant) with established psychometric properties — use those item-sets directly. Others (PHQ-9, HEXACO) have no Informant version; the inference variant is a **cleanroom adaptation** of the same items, same lineage as MMPI-inspired-cleanroom.

## Architecture — three layers

### Layer 1 — Instrument plug-in

```
reports/_engine/instruments/<slug>/
  instrument.yaml              # meta + licence + default-version + inference-config
  v<semver>/
    items.yaml                 # ordered items + reverse-codes + subscale-membership + substrate_inferable + scope
    scoring.py                 # optional; default = sum-with-reverse via lib/likert.py
    cutoffs.yaml               # optional banding/thresholds
    render.md.j2               # markdown report template
    source.py                  # optional; substrate-derived adapter for non-form instruments
```

**Versioning per instrument is load-bearing.** Lets you run `phq-9/v1.0.0` and an experimental `phq-9/v1.1.0-modified-wording` as separate parallel studies without conflict — the original use-case for this whole architecture.

`instrument.yaml`:

```yaml
slug: phq-9
title: "Patient Health Questionnaire-9"
domain: depression
licence: public-domain
licence-source: "Pfizer Inc., public domain"
construct: "Major Depression severity, DSM-IV criteria"
default-version: "1.0.0"
likert: 0-3
scoring: standard-sum
total-cutoffs:
  - {min: 0,  max: 4,  band: "minimal"}
  - {min: 5,  max: 9,  band: "mild"}
  - {min: 10, max: 14, band: "moderate"}
  - {min: 15, max: 19, band: "moderately-severe"}
  - {min: 20, max: 27, band: "severe"}
inference:
  enabled: true
  min_confidence: 0.75          # conservative default; operator-decided
  bandable_coverage_pct: 80     # below this, score is partial-not-bandable
  llm: claude-opus-4-7
  curiosity_fallback: false     # auto-curiosity only for substrate_inferable: false items
  max_curiosity_per_run: 3
```

`items.yaml` (excerpt):

```yaml
- id: 3
  text: "Schwierigkeiten beim Ein- oder Durchschlafen oder vermehrter Schlaf"
  scale: 0-3
  substrate_inferable: true
  scope:
    - source: oura
      lookback_days: 14
    - source: voice
      keywords: [schlaf, müde, wach, durchschlafen]
      lookback_days: 14
    - source: daily
      lookback_days: 14

- id: 6
  text: "Schlechte Meinung von sich selbst — Gefühl ein Versager zu sein."
  scale: 0-3
  substrate_inferable: false        # interner State, kein verlässliches Substrate-Signal
  fallback: curiosity                # auto-enqueue into operator-facing curiosity
```

The `substrate_inferable: bool` field is **curated once per instrument** at intake (~1 hour of work per instrument), then deterministic. It's the moral core of the methodology — what the substrate can honestly reach vs. what truly requires self-report.

### Layer 2 — Study container

A study = manifest declaring "which instruments at which versions with which source-mode and which schedule". Studies are the parallelism unit.

```
reports/studies/<study_id>/
  manifest.yaml
  runs/
    2026-05-17T15-30/
      phq-9.md
      gad-7.md
      ipip-neo-120.md
      _summary.md           # cross-instrument convergence/divergence flags
    2026-08-17T09-00/
      ...
  timeline.md               # longitudinal across all runs of this study
```

`manifest.yaml`:

```yaml
study_id: longitudinal-baseline
title: "Quarterly self-cartography baseline"
created: 2026-05-17
schedule: "quarterly"           # quarterly | monthly | weekly | manual
instruments:
  - {slug: phq-9,        version: 1.0.0, source: inferred}
  - {slug: gad-7,        version: 1.0.0, source: inferred}
  - {slug: asrs-v1.1,    version: 1.0.0, source: inferred}
  - {slug: ipip-neo-120, version: 1.0.0, source: inferred}
  - {slug: pid-5-bf,     version: 1.0.0, source: inferred}
  - {slug: meq-19,       version: 1.0.0, source: inferred}
  - {slug: chronotype-from-substrate, version: 1.0.0, source: substrate}
notes: "Baseline study; do not delete."
```

Parallel studies are then trivial:

```bash
wiki study new mmpi-cleanroom-v0.1 --fork-from longitudinal-baseline
# edit manifest: add mmpi-inspired-cleanroom/v0.1.0
wiki study run mmpi-cleanroom-v0.1
```

Self-vs-Informant comparison study:

```yaml
instruments:
  - {slug: phq-9, version: 1.0.0, source: inferred, alias: phq-9-inf}
  - {slug: phq-9, version: 1.0.0, source: form,     alias: phq-9-self}
```

Two runs of identical instrument, different source. `_summary.md` flags divergences.

### Layer 3 — `_engine/lib/` (the DRY backbone)

The reuse hebel. New instruments are 30 lines of YAML; nothing else changes.

- `likert.py` — scale-agnostic scoring (0-3 / 1-5 / 1-7), reverse-coding from items.yaml
- `subscale.py` — facet aggregation (IPIP-NEO 30, HEXACO 24, PID-5 25)
- `cutoffs.py` — config-driven banding
- `inference.py` — substrate-scope-resolver + agent-caller + JSON-schema-validator. Wraps `claude_agent_sdk` with `StderrCapture` + `classify_failure` (mirrors `scripts/core/sdk_helpers.py` pattern). Enforces 3-layer scope-lock: prompt + `disallowed_tools=Write/Edit` + `setting_sources=["project"]` (per `substrate-is-subject-not-instruction` memory).
- `provenance.py` — structured evidence records (file + line + snippet)
- `curiosity_bridge.py` — `enqueue_unresolved_item(study_id, instrument, item_id, item_text)` writes into existing curiosity queue with origin-tag (Ollama generates friendly question wording, consistent with no-silent-provider-fallback rule).
- `source/form.py` — interactive CLI form (rich-prompt) + Obsidian Meta-Bind variant (for the rare `source: form` study or the curated curiosity-fallback subset)
- `source/substrate.py` — adapter pattern for behavioral-derived instruments
- `timeline.py` — run-history aggregation, sparkline + matplotlib-PNG
- `compare.py` — `diff run_a run_b`, signed delta + band-crossing flags + evidence-shift flags
- `render.py` — j2 layer with standard partials (header / score-block / subscale-table / timeline / interpretation-notes / convergence-flags)
- `crosscheck.py` — cross-instrument convergence/divergence flags within a run

## Inference flow (single run)

For each instrument in the study, one pass:

1. **Scope resolve** — aggregate `scope` declarations across all items → minimal substrate-read set
2. **Single read** — agent loads that substrate into context (one call, not per-item)
3. **Score all items in one structured pass** — agent returns JSON:
   ```json
   {
     "items": {
       "1": {"answer": 1, "confidence": 0.82, "evidence": ["daily/2026-05-10.md#L34", "raw/notes/voice/2026-05-12.md"], "reasoning": "..."},
       "3": {"answer": 2, "confidence": 0.91, "evidence": ["..."], "reasoning": "..."},
       "6": {"answer": null, "confidence": 0.0, "reason": "substrate_inferable=false"}
     }
   }
   ```
4. **Per-item threshold check** — `confidence < instrument.min_confidence` (0.75 default) → mark unanswered
5. **Curiosity-fallback** — only triggers for items with `substrate_inferable: false` OR explicit operator-promotion via `wiki study promote-to-curiosity`. Other low-confidence items stay unanswered; next run retries as substrate grows.

Single-read instead of per-item-call is the DRY/cost optimization. IPIP-NEO-120 = one Claude-SDK call (~30–80 K tokens input, ~3K output), not 120.

## Conservative confidence policy + Coverage-as-first-class

**Default `min_confidence: 0.75`.** Per-instrument override in `instrument.yaml`. Rationale: operator wants scores they can trust, and is willing to wait quarters/years for the wiki to fill in.

Consequence: **Coverage becomes first-class**. Score alone is insufficient — every item is answered / unanswered, and a PHQ-9 with 4/9 items inferred has no interpretable Total Score. Run frontmatter carries:

```yaml
coverage:
  answered_at_high_confidence: 4
  total_inferable_items: 8         # items with substrate_inferable: true
  total_items: 9
  coverage_pct: 50                 # 4 / 8
  bandable: false                  # below bandable_coverage_pct → no band emitted
first_full_run: null               # set on first run where coverage_pct ≥ bandable threshold
```

`bandable: false` blocks premature clinical interpretation. The report says honestly "not yet scoreable, X items missing".

**Timeline becomes a double-plot.** Sparkline shows two curves over runs: Score (when bandable) + Coverage% (always). Coverage monotonically rises as substrate grows; Score only appears once Bandable threshold is reached. This **is** the "wiki grows into the instrument" visualization the operator wants.

## Curiosity-fallback policy

Stays minimal — operator hates auto-flooding:

- **Auto-enqueue:** only for `substrate_inferable: false` items. These are truly internal states (worthlessness, suicidal ideation, specific emotional textures) that have no substrate footprint by design. Asking is the only honest path.
- **Stay-unanswered:** `substrate_inferable: true` items with `confidence < 0.75`. No curiosity trigger. Substrate grows naturally; next run retrieves more. Patience is the design intent.
- **Manual escape hatch:** `wiki study promote-to-curiosity <study> <instrument> <item>` — operator-triggered, sees the item, decides it's worth asking now. Visible, deliberate.

Maps cleanly to operator's stated preference: "ggf curiosity, nur wenn es nicht anders geht."

## Provenance persistence + Drift detection

Each run stores per-item evidence-paths permanently. Run N+1 starts not from zero — it can read "Item 47 in Run N was 0.81 with evidence X, Y; is that evidence still valid in current substrate?" This enables:

- **Convergence checks** — same item, same score, same evidence across runs = stable signal
- **Drift flags** — same item, different score, different evidence = real change; report surfaces "Item 47: 4 → 2, evidence shifted from poetry-mentions in Q2 voice to absence-of-art-references in Q3"
- **Substrate-attribution drift** — same item, same score, different evidence = wiki found new support; informational, not concerning

This is methodologically unusual but cheap-by-architecture. Classical longitudinal studies cannot explain *why* an item shifted. This setup can.

## Instrument catalog (initial 35)

All public-domain or free-for-research unless explicitly flagged. Cleanroom-flagged where required.

**Personality — trait**
- IPIP-NEO-120, IPIP-NEO-300 (Goldberg, PD) — Big Five + 30 facets
- HEXACO-PI-R-60 (Lee & Ashton, free research) — adds Honesty-Humility
- BFI-2 (Soto & John, free research) — Big Five alternative cut
- TIPI-10, Mini-IPIP-6-20 (PD) — ultra-short, weekly-frequency viable
- OEJTS (Open Extended Jungian Type Scales, PD) — MBTI-flavored typology, no licence issue

**Personality pathology — MMPI zone**
- PID-5, PID-5-BF-25 (DSM-5 dimensional, APA PD) — modern MMPI personality replacement
- PiCD (ICD-11 personality, free)
- SAPAS-8 (8-item screen, free)
- **MMPI-inspired-cleanroom v0.1** — items derived from publicly-described PSY-5 construct definitions + IPIP item-bank as proxy. ~150-300 items. Multi-week construction. Self-test-retest = validation. Explicitly not an MMPI equivalence claim.

**Mood / anxiety / stress**
- PHQ-9, PHQ-2 (Pfizer PD)
- GAD-7 (PD)
- K10 / K6 (Kessler, PD)
- PSS-10 (Cohen, free)
- WHO-5 (PD)
- SWLS-5 (PD)

**Trauma**
- PCL-5 (NCPTSD PD)
- ACE-Q (PD)

**Substance use**
- AUDIT-10, AUDIT-C (WHO PD)
- DAST-10 (Skinner PD)
- CAGE-4 (PD)

**Burnout**
- OLBI — Oldenburg Burnout Inventory (free, Maslach alternative)
- CBI — Copenhagen Burnout Inventory (free)
- **MBI-cleanroom v0.1** — if Maslach axes are desired separately, cleanroom-derived

**ADHD / executive function**
- ASRS-v1.1 (WHO PD) — standard 6+12
- ASRS-5 (2017, 6 items)
- WURS-25 (Wender Utah, PD) — retrospective childhood

**Sleep / chronotype**
- MEQ-19, rMEQ-5 (Horne & Östberg, free)
- MCTQ (Munich ChronoType, Roenneberg, free) — Oura-cross-validatable
- PSQI (free non-commercial)
- ISI (Insomnia Severity, free research)
- ESS (Epworth Sleepiness, free research)

**Cognitive style**
- NFC (Need for Cognition, Cacioppo & Petty, free)
- CRT-7 (Cognitive Reflection, Frederick, free) — 3–7 items, highly replicated
- REI (Rational-Experiential Inventory, free)

**Impulsivity / self-regulation**
- BIS-11 (Barratt, free research)
- UPPS-P (free research)
- BSCS (Brief Self-Control, Tangney, free)

**Attachment**
- ECR-R / ECR-S (Experiences in Close Relationships, free research)

**Values / moral**
- PVQ-RR (Schwartz Portrait Values, free research)
- MFQ-30 (Moral Foundations, free)

**Mindfulness / self-compassion**
- SCS (Self-Compassion Scale, Neff, free research)
- MAAS (Mindful Attention Awareness, free research)

**Function / disability**
- WHODAS-2.0 (WHO PD) — cross-domain function

**Behavioral-derived (substrate, no form)** — same plug-in interface, different source type
- `chronotype-from-substrate` (Oura + Calendar + commit-time)
- `activity-rhythm` (producer-consumer-gap, session-length distribution)
- `ego-network` (people-pages × takes × meetings)
- `linguistic-trajectory` (LIWC-style over voice + sessions, NRC/VADER lexica, PD)
- `task-latency` (entity-page action-item Started→Done latencies)
- `affect-trajectory` (PANAS-style lexicon over daily + voice)

**Cleanroom strategy — what it means in practice**

For MMPI-inspired-cleanroom (and MBI-cleanroom if pursued):

1. No source-item access during construction.
2. Items generated from **publicly-described constructs** (DSM-5 trait facets for PSY-5; Maslach's three subscales are conceptually described in the published literature).
3. LLM as item-generator from those construct descriptions; operator-curated. Iteration log retained.
4. Pilot validation = self-test-retest over quarters against IPIP-NEO / PID-5 as convergence criterion. The study **is** the validation.
5. Licence: operator's item-pool, releasable under CC-BY if desired.

Realistic effort: ~2 weeks for a 150-item cleanroom instrument. One slice, not one milestone.

## Engine constraints honored

From existing memories — non-negotiable:

- **Substrate-is-subject-not-instruction** — `inference.py` agent calls must wire `disallowed_tools=[Write,Edit,NotebookEdit]` + `setting_sources=["project"]` + scope-locked prompt. Verbatim pattern from `scripts/compile.py`.
- **No-silent-provider-fallback** — inference = Claude SDK only. Curiosity-question wording = Ollama only. Never cross. Cross-provider escalation requires explicit `--allow-cloud` opt-in.
- **Compile-spawn-lock pattern** — `wiki study run` takes `flock` on `STATE_DIR/study-<id>.lock` so scheduled + manual triggers don't collide. Mirrors `scripts/compile.py` main-entry pattern.
- **Distill-don't-cite does NOT apply here** — reports are not wiki-substrate, they're an analytical surface. Citing `raw/` paths is the methodological core. Different surface, different rule.
- **Engine-vs-vault split** — instrument definitions are engine code (`.wiki/scripts/reports/instruments/…`). Study manifests + runs are vault data (`<vault>/reports/studies/…`). `wiki seed --force` ships templates for the first study (`longitudinal-baseline`).
- **Config-knob migration** — adding `features.operator_reports` + `personal.reports.studies_dir` etc. triggers `scripts/migrations/migrate_config_keys.py` extension in the same commit (per `feedback_config_change_requires_migration` memory).

## CLI surface

```bash
wiki instrument list
wiki instrument show <slug>
wiki study list
wiki study new <id> [--fork-from <other>]
wiki study run <study_id> [--instrument <slug>] [--source form|substrate|inferred]
wiki study diff <run_a> <run_b>
wiki study timeline <study_id>
wiki study promote-to-curiosity <study> <instrument> <item>
wiki report <slug>                    # ad-hoc one-off, not part of any study
```

## Touchpoints

- `scripts/reports/` (new sub-package) — engine code for instruments + lib
- `scripts/cli.py` — register `study`, `instrument`, `report` subcommands
- `scripts/core/config.py` + `config.example.yaml` — `features.operator_reports`, `personal.reports.*`
- `scripts/migrations/migrate_config_keys.py` — config-key migration in same commit
- `templates/reports/` (new) — seeded baseline study manifest + README
- `prompts/reports/infer_instrument.md` (new) — system prompt for the inference agent, scope-locked
- `prompts/reports/curiosity_question.md` (new) — Ollama-generation prompt for friendly curiosity-question wording
- `scripts/curiosity/` — existing curiosity-queue extended with `origin: study/<study_id>/<instrument>/<item>`
- `flush.py` — optional piggyback for scheduled studies (`schedule: quarterly` triggers from existing scheduler)
- `docs/architecture.excalidraw` + `docs/overview.excalidraw` — add `reports/` surface as a sibling of `knowledge/` with the air-gap explicitly drawn (per `feedback_infographics_track_engine`)
- `AGENTS.md` — schema doc + air-gap rule
- `.ytstack/DECISIONS.md` — record the air-gap as locked decision

## Lift estimate

This is an **L milestone**. Rough slice breakdown for the office-hours / plan-milestone phase to refine:

1. **S01 — Engine skeleton** (instrument loader, items.yaml schema, lib/likert + lib/cutoffs, single bandable instrument: PHQ-9-inferred end-to-end)
2. **S02 — Inference contract** (lib/inference, lib/provenance, scope-resolver, single-read agent, JSON-schema validator, 3-layer scope-lock pattern)
3. **S03 — Study manifest + runner** (manifest schema, runs/ dir layout, flock, schedule piggyback in flush.py)
4. **S04 — Coverage + timeline + compare** (lib/timeline, lib/compare, double-plot rendering, drift-detection flags)
5. **S05 — Curiosity bridge + form fallback** (curiosity_bridge.py, minimal CLI form for promote-to-curiosity path)
6. **S06 — Initial instrument catalog** (add ~10 baseline instruments: PHQ-9, GAD-7, ASRS-v1.1, K10, WHO-5, SWLS, ESS, MEQ-19, IPIP-NEO-120 stub, OEJTS stub)
7. **S07 — Behavioral-derived instruments** (chronotype-from-substrate, activity-rhythm, ego-network)
8. **S08 — First cleanroom (side-quest, optional)** — MMPI-inspired-cleanroom v0.1 item construction
9. **S09 — Closeout** (docs/architecture diagrams, AGENTS.md schema, DECISIONS air-gap entry, lxw seed)

S08 is optional and explicitly separable from the rest of the milestone.

## Risks

1. **Inference bias.** LLM systematically over-/under-calls symptoms based on substrate-distribution. Mitigation: `source: both` parallel studies (informant + self) as default for clinical screens; divergence flagged in `_summary.md`. Operator can sanity-check both numbers against lived experience.
2. **Coverage-stagnation.** Some instruments may never reach bandable coverage because the operator's substrate has structural gaps (e.g. attachment-style items need relationship-discussion substrate which voice/email rarely contains). Mitigation: visible coverage% in timeline makes this explicit, not silent.
3. **Air-gap leak.** Future me writes "compile.py should also read `reports/` for context" and the bias loop forms. Mitigation: hard rule in `AGENTS.md` + `DECISIONS.md`; lint check that warns if any prompt references `reports/`.
4. **Cost.** ~30 instruments × quarterly × ~2 large + ~28 small = a few dollars/year. Not a real risk, but watchlist if scope expands.
5. **Curiosity-flooding.** `substrate_inferable: false` items get auto-asked. Across 30 instruments this could be many items. Mitigation: per-instrument `max_curiosity_per_run` cap + global rate limit + curated-once `substrate_inferable` flagging (only truly internal states).
6. **Cleanroom legal misstep.** Accidental contamination of MMPI-cleanroom by exposure to original items. Mitigation: documented item-construction log; operator explicitly declares "I have not read MMPI items during construction"; releasability gate is operator-only judgement.
7. **Pathologization spiral.** Reports might encourage operator to read themselves clinically and chase scores. Mitigation: framing in `_summary.md` explicitly calls scores "longitudinal markers, not diagnoses"; bandable thresholds delay any clinical-flavored output until coverage is genuinely sufficient.
8. **Mobile-form abandoned.** `source: form` path will see little use given inference is default; investment in Obsidian Meta-Bind forms may go nowhere. Mitigation: defer Obsidian variant to S05-or-later; first form surface = CLI only.

## Ripens when

- Substrate has reached enough breadth that ~80% of common-screen items (PHQ-9, GAD-7, ASRS, WHO-5, MEQ) are plausibly inferable. Probably already true on lxw given current collector coverage.
- Operator wants longitudinal psychometric data they cannot currently get without committing to clinical assessment.
- Dream-cycle (`dream-cycle.md`) is **NOT** a prerequisite — these are independent surfaces. Dream-cycle synthesizes substrate into `knowledge/` (write); reports infer scores from substrate (read-only). They could land in either order.

## Status

**BACKLOGGED** — 2026-05-17. Architecture validated in conversation. Next steps if pursued:

1. `ytstack:office-hours` — stress-test premise with six forcing questions before any scaffolding
2. `ytstack:plan-ceo-review --mode concept` — scope-discipline check
3. `ytstack:plan-eng-review --mode concept` — feasibility check (especially inference-contract + scope-lock pattern)
4. `ytstack:init-project` or `ytstack:plan-milestone` (depending on whether this becomes its own .ytstack project or stays as a milestone in llm-wiki) — start scaffolding
