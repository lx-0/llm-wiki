# dream web-research — public-entity enrichment via Exa AI

**Source pitch:** GitHub issue [#2](https://github.com/lx-0/llm-wiki/issues/2) (@Sidwach, field request from a second operator vault).
**Size:** M-S (one producer + prompt + cooldown knob + sentinel writer; output infra already exists). **Cloud cost:** yes — Exa API, gated opt-in. **Status:** open — implementation started 2026-05-31 as an ad-hoc arc.

## Motivation

The dream cycle today deepens entity pages by re-reading **local substrate** (jamie/gmeet transcripts, daily captures). For **public individuals** — founders, executives, speakers — there's a parallel, never-tapped source: the public web. The operator reflexively googles new contacts; the wiki should replicate that reflex for public figures.

Concrete example (illustrative, fictional): a `knowledge/people/jordan-hale.md` compiled from a meeting transcript notes "runs a regional agency" but doesn't know they founded Brightwave Labs (one web search away).

Two goals: **reliability** (validate substrate-derived claims against public records) and **enrichment** (surface publicly available context the substrate never captured).

## Architectural placement — IMPORTANT

The issue frames this as "a new Producer in the producer registry, triggered post-dream." That framing is **half right** and must not be implemented literally:

- The existing `scripts/producers/` registry (`base.py` `Producer` Protocol) is **post-COMPILE-shaped**: `run(source: Path)` consumes a `raw/` source inside `compile.py`'s post-pass loop, gated by `enabled_config_key` + `source_glob_config_key`. It does NOT model "operate on a compiled `knowledge/people/<slug>.md` after dream synthesis."
- Web-research enrichment operates on a **compiled entity page**, triggered **post-dream**, for `type: person` entities only. That's a **dream post-pass**, structurally distinct from the compile producers.

→ Implement as a post-pass inside `dream.py` (after `dream_entity()` succeeds), NOT by shoehorning into the compile producer registry. If a shared "post-pass" abstraction is wanted later, that's a separate refactor — don't block this on it. Note the divergence in CONTEXT.md so the Producer vocabulary stays honest.

## Design

### Opt-in — two gates, both required

1. **Vault flag:** `features.dream_web_research: false` (default off).
2. **Per-entity opt-in:** frontmatter `web_research: true` OR reserved tag `public-person`. Never fires on every person page.
3. **Cooldown:** `scheduling.web_research_cooldown_days: 30` (separate from the dream cooldown — public profiles change slowly).

### Backend

Configurable, default `exa` (Exa AI neural search). API key from `personal.exa_api_key` or env `EXA_API_KEY`. The `exa-search-api` skill already documents the request pattern — reuse it (don't re-derive the API shape from memory; live-probe once per `feedback_live_probe_before_parser`). Backend abstraction so `serper`/`brave` can slot in later, but ship only `exa`.

### Output — sentinel-managed block, air-gapped from compile

A dedicated `## Public Profile` section, sentinel-delimited (`<!-- web-research:begin -->` … `<!-- web-research:end -->`), same pattern as the M020 backlinks footer (`features.materialize_backlinks`). The block:

- Is clearly labeled web-sourced (`_auto-researched · last updated: <date> · source: exa_`), structurally separate from the compiled `## State` / `## Timeline`.
- Is **never written back into `raw/`** — this is the load-bearing constraint. Feeding web text into `raw/` would let the compiler re-synthesize it as if operator-authored (compile-loop contamination). Cross-check `project_distill_dont_cite`: provenance via frontmatter, not body injection.
- Refreshes on its own cooldown, idempotent (re-run replaces the block in place).

### Integration point

Post-pass inside `wiki dream <slug>` when: `features.dream_web_research` ∧ (`web_research: true` ∨ tag `public-person`) ∧ cooldown not active. Also standalone: `wiki dream --web-research-only <slug>`.

## Affected files

- `scripts/core/config.py` — `Features.dream_web_research: bool = False`; `Personal.exa_api_key: str = ""`; `Scheduling.web_research_cooldown_days: int = 30`.
- `scripts/migrations/migrate_config_keys.py` — add all three to `KEY_ADDITIONS` (same commit — config-change rule).
- `scripts/web_research.py` (or `scripts/producers/web_research.py` if a dream-post-pass home is carved) — Exa client + block builder + sentinel writer + cooldown gate.
- `scripts/dream.py` — post-pass hook after `dream_entity()`; `--web-research-only` arg; standalone CLI path.
- `prompts/web_research_entity.md` — system + user prompt (per `feedback_prompts_in_prompts_folder` — never inline Python strings).
- `config.example.yaml` — document the three keys.
- `tests/` — sentinel block idempotence, cooldown gate, `raw/`-never-written assertion, gate-logic (flag off / no per-entity opt-in → no-op).
- `docs/architecture.excalidraw` + `docs/overview.excalidraw` — add a "Public Profile (web)" chip to the dream-cycle pillar (steady-state, no milestone badge).

## Reconciles-with — locked decisions to respect

- **Cloud-cost reality** (`feedback_cloud_video_cost_reality`): Exa is external/paid. The double-opt-in (vault flag + per-entity) + 30d cooldown is the `--allow-cloud`-equivalent posture. Default off.
- **No silent provider fallback** (`feedback_no_silent_provider_fallback`): web-research is its own provider lane; it does NOT fall back to Ollama/Claude and the dream cycle does NOT fall back to it. Explicit opt-in only.
- **Distill don't cite** (`project_distill_dont_cite`): the `## Public Profile` block is provenance-labeled and never re-enters `raw/`; the compiler must not treat it as operator substrate.

## What should NOT happen

- Web results must NOT flow into `raw/` (compile-loop contamination).
- The block must be visually + structurally distinct from compiled `## State`.
- Must NOT fire automatically on every person page — opt-in per entity or per vault.
