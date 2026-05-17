# Takes substrate — third-party belief attribution

A separate substrate that records "WHO believes WHAT, with confidence + when + source". Adopted from gbrain's Facts/Takes split (`docs/takes-vs-facts.md`). See `gbrain-comparison.md` for context.

## The gap it fills

llm-wiki currently has:

- `knowledge/facts/<slug>.md` — operator-stated hard facts with trust tier (confirmed/asserted/provisional). Owner-only.
- `daily/YYYY-MM-DD.md` — sessions, including quotes attributed to people.
- `raw/transcripts/jamie/*.md` — meetings with diarised speakers.
- `knowledge/concepts/*.md` — distilled ideas; provenance via `compiled_from`, but the *person* who held the belief is lost in distillation.

What's missing: a way to capture *"Jane Doe thinks GPT-5 will commoditize agent platforms (high confidence, said 2026-04-15 in Jamie meeting `abc123`)"*. Currently this either disappears in distillation or pollutes `facts/` (which is meant for *your own* corrections, not others' opinions).

## The proposed shape

```markdown
---
title: "Takes — Jane Doe"
type: takes
holder: jane-doe
last_updated: 2026-05-13
---

# Takes — Jane Doe

- **2026-04-15** [high] · `raw/transcripts/jamie/2026-04-15--review--abc.md` — GPT-5 commoditizes agent platforms within 12 months.
- **2026-03-02** [medium] · `daily/2026-03-02.md` — Inference cost will halve every 9 months, not 6.
- **2026-02-10** [low] · `raw/notes/email/acme-2026-02-10.md` — "Agent infra is a feature, not a product." (offhand)
```

One file per holder. Append-only. Confidence is a small enum (`low`/`medium`/`high`). Belief is one prose line — full context lives in the cited source.

Alternative shape: one global `knowledge/takes.md` file with all takes across all holders, sorted by date. Simpler grep, harder to read per-person. Decide in pitch.

## Where takes come from

- **Compile-pass producer.** When `compile.py` distills a `daily/`-entry or `raw/transcripts/`-file, it emits takes alongside the regular knowledge update. New prompt path; small extra cost per compile.
- **Operator-typed.** `wiki take add jane-doe "GPT-5 will commoditize..." --confidence high --source raw/transcripts/jamie/2026-04-15.md` — analogous to `wiki correct add`.
- **Dream-Cycle synthesis** (see `dream-cycle.md`) — once-per-N-days pass that promotes recurring beliefs across sessions into takes.

Probably all three, layered.

## How takes are consumed

- **Compile prompt** loads relevant takes when distilling a person-page (entity-state for Jane includes "what she believes" pulled from `knowledge/takes/jane-doe.md`). Asymmetric with `facts/`: facts override, takes inform.
- **Query prompt** can answer "what does Jane think about X?" by grepping the takes substrate.
- **Lint** can flag takes that contradict each other or contradict `facts/`. New check `check_takes_consistency`.
- **Dashboard** — eventually a "recent takes by you" panel, surfacing patterns. Defer.

## Open questions

- **Substrate boundary.** Is `knowledge/takes/` part of `knowledge/` (LLM-owned) or `raw/takes/` (operator-curated)? Recommend `knowledge/takes/` because the compile-pass producer is the main writer; operator commands write through compile-stage helpers, not direct edits.
- **Holder identity.** Slug = `jane-doe` (kebab-case canonical name). What when slug collides with `knowledge/people/jane-doe.md`? Probably fine — different folders, related entity, both can exist.
- **Confidence rubric.** What does "high" mean? Probably: stated multiple times, recently, consistently → high. Said once offhand → low. Document in `prompts/extract_takes.md`.
- **Owner takes?** Does the operator's own session-quoted beliefs land in `takes/alex.md`, or stay in `facts/`? gbrain explicitly separates them; llm-wiki could do the same — own beliefs → `facts/`, others' beliefs → `takes/`.
- **Promotion path.** When a take is confirmed externally, does it become a `facts/` entry? Or does the take stay where it is and gain a `verified: 2026-05-13` field? gbrain's dream-cycle does the former; llm-wiki could go either way.

## Touchpoints

- `prompts/compile_main.md` — add a "Takes extraction" sub-section. Optional output: zero, one, or many `takes/<holder>.md` append-lines per compiled source.
- `scripts/compile.py` — new helper `extract_and_append_takes()` after the main compile output. Pattern mirrors `maybe_generate_curiosity_requests`.
- `scripts/facts/take.py` (new) — `wiki take add/list/remove/show` CLI; mirrors `correct.py` shape.
- `scripts/lint.py` — `check_takes_consistency` (LLM-driven, similar to contradiction check).
- `prompts/query_main.md` — augment the facts-loading block to also load relevant takes when the query mentions a known holder.
- `templates/AGENTS.example.md` — schema doc.

## Lift estimate

- Prompt extension + extractor wiring: 1 day
- `wiki take` CLI + tests: 1 day
- Lint check: 0.5 day
- First-pass dogfood on 10 recent daily-files + 6 Jamie meetings: 1 day

**~3.5 days end-to-end** for the producer + CLI. Lint and dashboard surfaces add another 1-2 days.

## Risks

1. **Takes become noisy.** Every session has minor offhand opinions; substrate fills with low-signal entries. Mitigation: extraction prompt requires explicit confidence + verifiable phrasing; "I think maybe X" gets dropped.
2. **Holder attribution wrong.** LLM mis-attributes a belief to the wrong speaker. Mitigation: structured citation field linking back to the source file with line-anchor or quoted phrase; lint warns if quote can't be grep-found in the source.
3. **Drift between takes/ and facts/.** Operator says "I agree with Jane" — does it become a fact (owner-belief) or stay as a take? Document the rule clearly: facts = self-attribution, takes = third-party attribution. Both can exist for the same proposition.
4. **Cost.** Extraction adds tokens per compile call. Mitigation: opt-in via `features.extract_takes` (default off until producer-quality is verified).

## Ripens when

- Jamie meetings start producing speaker-attributed beliefs that operator wants to track across time (probably within 20-30 meetings).
- OR operator asks "what did X think about Y last quarter?" and has to grep transcripts.
- OR Dream-Cycle (`dream-cycle.md`) lands — takes are the natural output substrate for cross-time synthesis.

## Status

**SHIPPED** via M011 (ba63c1c, 2026-05-16, Agent D). See commit message + git log for implementation details. Backlog kept as decision-context.