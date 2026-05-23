# Health trend-synthesis — turn 11 years of metrics into knowledge

**Status:** MVP SHIPPED 2026-05-23 — deterministic layer (`wiki health-trends`, `scripts/health_trends.py`). Surfaced when the operator asked "the 1500 health days just get skipped — shouldn't they be compiled?". Phases Concept→Verify→Implement→Document (PROCESS §15 + AGENTS + README + KNOWLEDGE). **Phase 5 (Visualize): no diagram edit** — per CLAUDE.md steady-state rule, a default-off niche routine with no existing synthesis cluster to fold into (dream-cycle isn't depicted either) lives in PROCESS.md, not architecture.excalidraw. If the synthesis layer ever earns a slot, do it as ONE synthesis/aggregation cluster (dream-cycle + health-trends + entity-pages), not a one-off box.

**Deferred (future, not built):** LLM narrative ("HRV fell in Q1…"); cross-substrate correlation (health × calendar/voice/mood); `MOCs/health.md` hub; sparkline charts.

## Why

The per-day health stub is correctly NOT knowledge (per `concepts/health-rollup-intake-format.md`: "a single day's numbers are point-in-time data, not knowledge … contributes nothing beyond a log-line"). The deterministic skip (2026-05-22) made that cheap and stopped the max_turns bloat. But the policy explicitly defers the *real* value to **"(b) future trend aggregation across many days"** — which does not exist. So today:

- `raw/notes/health/` holds **2602 days** (Oura 2022-2026 + HealthKit XML 2014-2026; gap 2019-2021).
- They reach knowledge only as scattered **per-day daily-digest mentions** in `knowledge/concepts/health.md` (11 Timeline lines like "Short sleep 3.9h, readiness 64") — point-in-time, not trends.
- Nothing produces **baselines, trends, anomalies, or correlations** — the knowledge a self-cartography engine should hold about the operator's body.

This is the missing **synthesis consumer** the intake-priority decision (`DECISIONS.md` 2026-05-22) says must exist before a substrate earns its keep. Health substrate is already ingested at scale; the consumer is the gap.

## What (sketch)

A periodic **health-trend synthesis** that reads the health metric corpus and writes a real trends layer into `knowledge/concepts/health.md` (or a `knowledge/MOCs/health.md` hub).

Two layers, deterministic-first (per the project's "no agent for deterministic actions" rule):

1. **Deterministic aggregation (no LLM).** Walk `raw/notes/health/**` frontmatter, compute per-metric rolling stats over windows (weekly / monthly / quarterly / yearly): mean, min/max, trend slope, current-vs-baseline delta, coverage (which metrics exist per era — sparse 2014-2018, rich Oura 2022+). Pure Python over the YAML frontmatter — cheap, idempotent, no SDK. Renders a stats/chart block (reuse the dashboard chart machinery).
2. **Narrative synthesis (LLM, thin).** An agent reads the *aggregates* (not 2602 raw files) + recent life-context, and writes a short "what changed and when" State block: "HRV trended down through Q1 2026; sleep-debt cluster around <window>". Strict: present trends + **flag** candidate correlations, never assert causation.

## Reuse (low-hanging)

- **dream-cycle pattern** (`dream.py`): cross-time synthesis, cooldown, cost caps, piggyback, dry-run — but the corpus here is a *metric series*, not entity-mentions, and the aggregation is deterministic. Likely a sibling routine, not a dream extension (same lesson as reconcile: don't bend dream's entity-corpus shape).
- **Deterministic health stub path** (`compile.py::_health_rollup_body_is_stub`): the frontmatter-parse + metric-extraction is already there; reuse for aggregation.
- **`knowledge/concepts/health.md`**: the consumer page already exists (digest-seeded stub "can flesh out once the pattern stabilizes").
- **Dashboard charts** (M003): render trend sparklines/timelines.

## Open design questions

- **Windows + cadence:** rolling weekly/monthly/quarterly? Synthesis cadence (health changes slowly → monthly piggyback, not per-compile).
- **Output home:** State block on `concepts/health.md` vs a dedicated `MOCs/health.md` trend hub vs a `type: moc` trend rollup (the policy article hints at `type: moc` for "trend rollups").
- **Deterministic-only vs +LLM-narrative:** ship the stats layer first (cheap, useful), add narrative later?
- **Correlation scope:** health-internal trends only (safe) vs cross-substrate correlation with calendar/voice/mood (much bigger, speculative — separate milestone). Start health-internal.
- **Sparse/era coverage:** HealthKit 2014-2018 has only distance/flights/weight/steps; Oura adds sleep/hrv/readiness 2022+; 2019-2021 gap. Trends must be coverage-aware (don't draw a "sleep trend" across years with no sleep data).

## Edge cases

- **No double-count:** Oura vs HealthKit overlap already deduped at ingest (M023); aggregation reads the merged per-day files, so it inherits that.
- **Idempotency / cost:** deterministic layer is free + idempotent; LLM layer gated by cooldown + cost cap (dream pattern).
- **Don't re-bloat:** aggregation writes ONE trends block (sentinel-managed, like backlinks footer), not per-day entries — the opposite of the compiled_from bloat that started this whole thread.

## Related

- `concepts/health-rollup-intake-format.md` (the policy that defers "(b) trend aggregation")
- `.ytstack/backlog/shipped/health-collector.md`, `project_health_phase_1_shipped`, M023 HealthKit XML bulk-ingest
- `DECISIONS.md` 2026-05-22 (intake = persona-coverage; synthesis consumer must exist) + `consumption-curiosity-axis.md` (same "consumer is the gate" principle)
- dream-cycle (`dream.py`) — the cross-time-synthesis sibling
