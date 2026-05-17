# Dream-cycle — sampled-activation + conflict-aware corpus (M016)

**Status:** shipped 2026-05-17 (M016). Supersedes the naive M014 "load all
substrate mentioning slug" approach.

## Why this exists

M014 (`scripts/dream.py`) collected the *full set* of substrate files that
named an entity slug, truncated each at 8 KB, and shipped the lot to the
SDK. That worked for thin entities (≤30 substrate files); it collapsed on
the operator's own page `alex.md` on lxw, which had ~475 mentioning files
totalling ~2.3 MB after truncation. Symptom: SDK exit-1, empty stderr,
`kind=unknown` — Claude's silent context-overflow signature.

Throwing more context window at it (the 1M variant) only delays the
crash and makes each crash burn more dollars. The fix is **architectural**:
bound the corpus size per dream + sample the older substrate so every file
eventually gets fresh LLM eyes over a window of dreams, instead of every
file being re-read on every dream.

## Research grounding

The pattern below is **Sleep-Consolidated Memory** as it appears in 2026
production-LLM memory literature. We are NOT inventing this; we are
adopting it. Key references that shaped the design (read them before
deepening — none are vendored):

- **SCM — Sleep-Consolidated Memory (2026)** — bounded working memory +
  importance tagging + NREM/REM consolidation cycles + adaptive forgetting
  (reports ~90% noise reduction on long-running agents).
- **SleepGate (arXiv:2603.14517)** — conflict-aware temporal tagger,
  forgetting gate, consolidation as a *reshape* (not append) operation.
- **A-Mem (arXiv:2502.12110)** — Mix-of-Experts gating, learned weights
  combining semantic similarity + recency + importance for memory
  activation. We use a deterministic version of the weight formula
  (no learned weights yet — that's M018 territory).
- **MemGPT / Letta — tiered memory** (core / recall / archival). We map
  this to Tier 1 (always-include) / Tier 2 (sampled) / Tier 4 (digest).

## The 4-tier architecture

Per `dream-entity <slug>` invocation:

### Tier 1 — always-include (target ≤200 KB)

Hard-included on every dream. The entity's identity is load-bearing
context; never evict.

- All files with `author: <slug>` in frontmatter, **OR** `compiled_from:`
  listing the slug, **AND** `compile_role: source-and-final` (operator-
  authored knowledge — concepts, personal-* pages, etc.). These cover
  the operator's own deliberate writing about themselves; without them
  themed sections (## Music, ## Games, etc.) never emerge because the
  substrate is all third-party.
- The entity page itself (the State to reshape).
- Last `dream_tier1_recent_count` (default 20) most-recent substrate
  files mentioning the slug, sorted by mtime descending.
- Last `dream_tier1_digest_days` (default 7) `daily/<date>.md` digests
  (the M001 compressed-substrate rollups — these are already digest-shaped,
  so they pack a lot of signal per KB).

### Tier 2 — weighted probabilistic sample of older substrate (target ≤400 KB)

For substrate older than Tier 1 covers, sample `K = dream_tier2_sample_count`
(default 50) files via a deterministic activation score:

```
score = importance × recency_decay × dreams_since_last_seen × (1 + noise)
```

- **importance** — content-type weighting:
  - `raw/memories/`                      → 3.0
  - `raw/transcripts/{jamie,gmeet}/`     → 2.0
  - `raw/notes/longform/`                → 1.5
  - `raw/notes/{email,calendar}/`        → 1.0
  - `raw/notes/screenshots/`             → 0.8
  - default                              → 1.0
- **recency_decay** — `1 / (1 + days_since_mtime / 90)`. Soft 90-day
  half-life — older content competes but doesn't vanish.
- **dreams_since_last_seen** — `max(1, days_since_last_dreamed_at)` read
  from the substrate file's `last_dreamed_at:` frontmatter. New files
  (no stamp) get a very large value (1e6) so they're guaranteed
  fresh-LLM-eyes on the first dream after import.
- **noise** — `random.uniform(0.85, 1.15)`. Small jitter so identical-score
  files don't tie in stable order.

Top-K by score are included. Each included file gets its
`last_dreamed_at: <iso-today>` frontmatter stamped after the dream runs
(write-back), so the score's `dreams_since_last_seen` term cycles files
through the sampling pool over time.

**Cycling rate math:** at K=50, vault of 1000 older files, mean
re-sampling interval is 1000/50 = 20 dreams. At default `dream_cooldown_days=7`
that's ~140 days between fresh-LLM-eyes per file — too long for highly
recent files (handled by Tier 1) but acceptable for older substrate where
the dream's job is "did anything in here reshape the entity's State?".

### Tier 3 — conflict-aware reshape (prompt-side)

This is **not a code tier** — it's a mandate in `prompts/dream_entity.md`
that turns the LLM from an appender into a reshaper.

The MVP prompt told the model to "synthesize the State block from the
corpus". That works for fresh entities but is wrong for established ones:
when the corpus contains substrate that **contradicts or refines** the
existing State, the model would typically append "Note: now X" rather than
*reshape* State to reflect the new reality and demote the old claim to
Timeline with a `_(superseded YYYY-MM-DD by [new substrate])_` annotation.

The Tier 3 mandate (see `prompts/dream_entity.md` Step 2 block) makes
re-evaluation explicit. Without it, dream-cycle is just a bigger compile.

### Tier 4 — hierarchical digest (already shipped, M001)

`daily/<date>.md` rollups are the M001 digest substrate — already aggregated
at the day granularity. Tier 1 pulls the last 7 days of them directly. No
new tier-building code in M016. Recursive weekly/monthly digest building is
deferred to M017 (`recursive-dream-cycle.md`).

## Cost guarantee

Bounded by construction:

- Tier 1 caps: ~200 KB total (20 recent files × ~8 KB truncation + 7 daily
  digests × ~3 KB + author-authored content typically ≤30 KB for a single
  operator).
- Tier 2 cap: K × per-file-truncation. K=50, 8 KB cap → 400 KB.
- Total corpus ≤ ~600 KB per dream. Pre-flight estimate (M014's
  `estimate_cost_usd`) still applies on top — operator's per-entity USD
  cap fires before any genuinely runaway prompt reaches the SDK.

This bound is independent of vault size. Whether `alex.md` has 50 or 5000
mentioning files, the per-dream corpus stays ≤600 KB.

## What this is NOT (deferred)

- **Recursive dream-cycle** (weekly→monthly digest building) — M017.
- **Strategic forgetting** based on access patterns (file archival /
  eviction from substrate) — needs telemetry first; M018.
- **Vector embeddings / RAG retrieval** — only worthwhile at vault scale
  >5000 files. Sampling is cheaper and deterministic until then.
- **Sleep-time async consolidation** (cron-driven dream-cycle running in
  background) — would replace piggyback wiring; M019.
- **Learned activation weights** (A-Mem style MoE gating) — needs ≥3
  months of dream-history to train against. Backlog.

## Config knobs added

All three live on `Limits`:

```yaml
limits:
  dream_tier1_recent_count: 20        # most-recent substrate files always-in
  dream_tier1_digest_days: 7          # last N daily rollups always-in
  dream_tier2_sample_count: 50        # weighted-sample size from older substrate
```

Migration injected the same defaults via `KEY_ADDITIONS` in
`scripts/migrations/migrate_config_keys.py` so existing operator vaults
pick the keys up on next `wiki update`.

## File touchpoints (this slice)

- `scripts/dream.py` — rewrite `collect_corpus()` per 4-tier spec.
  Add `_compute_sampling_score()`, `_get_last_dreamed_at()`,
  `_write_last_dreamed_at()` helpers. Plumb new config knobs.
- `prompts/dream_entity.md` — Tier 3 mandate (Step 2 block).
- `scripts/core/config.py` — three new `Limits` fields.
- `config.example.yaml` — operator-facing docs.
- `scripts/migrations/migrate_config_keys.py` — `KEY_ADDITIONS` for the
  three knobs (same-commit per CLAUDE.md hard-rule).
- `tests/test_dream_sampling.py` — Tier 1/2 mechanics, weight calc,
  last_dreamed_at tracking, conflict-aware prompt presence.

## Future-agent notes

When deepening:

1. **Don't** lift the importance constants into the prompt — they're
   selection heuristics, the LLM doesn't need to know them.
2. **Don't** add semantic similarity to Tier 2 scoring unless the
   embedding cost is justified. Greppable name-matching covers ~80% of
   "is this file about this entity" already; the rest is captured by
   Tier-1's author/compiled_from check.
3. **Do** revisit the noise term if dreams become deterministic-feeling
   to the operator — a wider band (0.7-1.3) trades coverage for
   diversity.
4. **Do** treat `last_dreamed_at` as a write-once-per-dream stamp.
   Multiple dreams of different entities on the same day can re-stamp,
   but a single dream-entity run never writes the same file twice in
   one pass.
