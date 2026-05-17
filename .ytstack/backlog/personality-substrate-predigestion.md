# Personality-substrate pre-digestion — R2 forward

Per-domain pre-digestion layer that lets personality instruments
(IPIP-NEO-120, HEXACO-PI-R-60, PID-5, PVQ-RR) run against operator
substrate without overflowing the SDK call's context window.

## Why this is needed

**M019-S02-T01 R2 audit on lxw (2026-05-17)** found:

| Instrument | Lookback | Files | ~Tokens | Headroom |
|---|---|---|---|---|
| phq-9 v1.0.0 (real) | 14d | 191 | 105,959 | 33.8% |
| ipip-neo-120 (synthetic stub) | 180d | 133 | 147,516 | 7.8% |

Wedge clinical screens (PHQ-9 / GAD-7 / ASRS-v1.1 / WHO-5 / K6, all
14-day lookback over voice + daily + health + transcripts) pass
comfortably. Personality instruments use a 180-day lookback over a
wider substrate set (adds knowledge/people/, takes/, longer voice
window) and **already sit at 92% of the 160K-token budget**. Another
1–2 months of substrate growth OR a scope widening (follow-citations
into linked concept pages, takes-substrate adoption) tips them into
overflow.

The pre-digestion layer is a **gating prerequisite** before
IPIP-NEO-120 or any of its siblings ship — not an optimisation to do
later.

## Three mitigation paths

### (a) RAG via embedding-similarity

Pre-compute embeddings for every substrate document. At inference
time, embed each item's text and pull top-K substrate documents by
cosine similarity. Hand only those K to the agent.

- **Pros:** classical RAG; well-understood; per-item targeting; cheap
  inference once embeddings are pre-computed.
- **Cons:** new dep (likely `chromadb` or `lancedb` or simpler `numpy`
  cosine); embedding-model selection is its own rabbit hole; cache
  staleness when substrate changes; loses cross-substrate context
  signal ("operator mentioned X in Tuesday's voice AND Wednesday's
  meeting" requires both, RAG might surface only one).

### (b) Per-substrate summarisation pass

Run a cheap classify_model (Ollama gemma4) over each substrate file
ONCE per lookback window, summarising into a ~200-token "what does
this file say about extraversion / openness / agreeableness /
conscientiousness / neuroticism / honesty-humility". Cache the
summaries. Agent reads concatenated summaries, not raw substrate.

- **Pros:** no new dep; Ollama already in the stack; summaries are
  human-readable (operator can verify); per-trait summaries match the
  facet structure of personality instruments.
- **Cons:** quality degradation depending on classify_model fidelity;
  cache invalidation needs careful handling; summarisation costs
  add up over 1000+ substrate files.

### (c) Per-subscale call-batching

Treat each personality facet (Big Five: 5 batches; HEXACO: 6
batches; PID-5: 25 batches) as its own SDK call with a narrowed
scope. Items 1-4 of IPIP-NEO (extraversion facet 1) get only the
people-pages + voice mentioning social events; items 5-8 (facet 2)
get a different scope; etc.

- **Pros:** uses the batched-by-subscale interface already shipped in
  M019-S02-T02; per-batch context stays small even if total
  substrate-volume grows; no new dep.
- **Cons:** 30+ SDK calls per IPIP-NEO run vs. 1 (cost multiplier);
  per-subscale scope-spec curation is real work (1-2 hours per
  instrument); some items resist clean facet-scope mapping.

## Hybrid recommendation

For wedge → post-wedge migration, the natural path is **(c) +
selective (b)**:

1. Personality instruments ship with batched-by-subscale interface
   already in place from S02-T02. Each batch handles its facet's
   subset of items.
2. For the broad substrate (knowledge/people/, takes/), add per-file
   summarisation via classify_model that produces a stable
   per-person trait-relevant blurb. Cache invalidates on file mtime.
3. Per-batch scope:
   - Trait-specific batches read only their relevant summarised
     substrate. E.g. extraversion facet reads people-pages
     summaries + meeting-frequency from calendar.
   - Domain-agnostic batches (Openness-Aesthetics: poetry, art
     mentions) read voice + daily over a wider window but with
     keyword filtering.

This composes existing engine pieces (Ollama summarisation +
batched inference + scope-spec) rather than introducing RAG dep.

## Cost projection

Wedge weekly clinical screens: 5 instruments × ~$0.17 = $0.85/run ×
52 = $44/year.

Personality post-wedge with hybrid (c+b):
- 4 personality instruments × 5–30 batches each = ~80 SDK calls
  per "personality run" (quarterly cadence).
- Per-batch cost similar to wedge clinical (~$0.10 at Haiku for the
  smaller scope) → 80 × $0.10 = $8/run × 4 = $32/year for the four.
- Summarisation refresh (1000 files × ~200 tokens × Ollama, local) =
  free in $-terms, ~30 minutes of wall-clock for full re-summarise.

Total post-wedge with personality landing: ~$76/year. Acceptable.

## Implementation plan (post-wedge)

1. **Slice 1** — Per-substrate-summarisation cache. New
   `scripts/reports/_engine/lib/summarise.py` reads substrate files
   via Ollama classify_model with a trait-keyword prompt. Caches
   under `state/reports-summarise/`. mtime-invalidated.

2. **Slice 2** — Per-subscale scope-spec for one personality
   instrument (IPIP-NEO-120 first). Adds `scope:` block to each
   item with `substrate_types` + optional `keywords`.

3. **Slice 3** — Token-budget audit extension. Audit script
   resolves scope per batch (not per instrument) and reports
   per-batch headroom. Validates the new architecture against
   actual lxw substrate before the live run.

4. **Slice 4** — IPIP-NEO-120 v1.0.0 with batched inference end-to-end.
   Single live run on lxw produces 30 per-batch reports + one
   composed instrument-report.

5. **Slice 5** — HEXACO-PI-R-60, PID-5-BF-25, PVQ-RR as YAML-only
   additions following the same pattern. Validity tests.

6. **Slice 6** — Closeout: DECISIONS entry locking the hybrid
   architecture; KNOWLEDGE on what worked / what didn't; backlog
   update if any further mitigations surface.

Rough size: M (~3-4 weeks).

## Ripens when

- Operator wants personality longitudinal data and the wedge clinical
  loop has been running ≥2 months (validates the consumption pattern
  before extending).
- OR substrate volume on lxw grows another 20% (audit headroom drops
  further; gating becomes pressing).

## Status

**BACKLOGGED** — captured 2026-05-17 by M019-S04-T06b. Wedge has not
yet shipped (S05 still pending); this stays gated behind wedge proof.
