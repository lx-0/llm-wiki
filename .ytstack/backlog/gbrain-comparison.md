# gbrain (Garry Tan) vs. llm-wiki — Architecture Comparison

Reference implementation analysis. gbrain at `github.com/garrytan/gbrain` (TS / bun / Postgres+pgvector, MIT, 15.4K stars, v0.26+, single-author Garry Tan / YC President). Companion analysis to `karpathy-comparison.md` and `meetily-intake.md`.

**Purpose:** Identify which gbrain patterns transfer to llm-wiki without breaking the Markdown-only / engine-vault-split bet, and which are deliberately not adopted.

## Why this comparison matters

gbrain defines itself **explicitly against** the static-wiki pattern: *"A static wiki stores compiled pages; GBrain continuously enriches."* — which is wordforword the architectural cut llm-wiki took. Both projects solve the same need ("personal knowledge for an agent that touches my data daily") with near-inverted trade-offs. Looking at where gbrain went and *why* surfaces where llm-wiki's bet is load-bearing vs. accidentally narrow.

## Profile

| Axis | gbrain | llm-wiki |
|---|---|---|
| Stack | TypeScript / bun / Postgres+pgvector / Claude | Python / uv / no DB / Claude + Ollama |
| Storage | Markdown + Postgres (PGLite default → Supabase >~1K files) | Markdown only |
| Retrieval | Hybrid: vector + keyword + RRF fusion, pgvector HNSW | Markdown read (grep + Dataview) |
| Write trigger | Continuous, per-signal | Batch: compile pass after hook/cron |
| Reported scale | 17,888 pages / 4,383 people / 723 companies (Garry's live) | ~668 nodes (lxw vault) |
| Ecosystem | OpenClaw/Hermes plugin, MCP server (stdio + OAuth 2.1), Recipes | Obsidian-native, multi-agent hooks (Claude/Codex/Gemini/Cursor) |
| Tests / eval | longmemeval, eval-cross-modal, P@5 49.1% / R@5 97.9% on benchmarks | 79 pytest, no IR-style eval |
| Maturity | 15.4K stars, productized, v0.26+ | Single-author prototype |

## Conceptual cuts

### 1. Compile vs. enrich-on-write

- **llm-wiki:** *Compile once, query fast.* Substrate → batch distillation → atomic articles. Wikilinks emitted by the LLM during compile.
- **gbrain:** *Brain-first lookup* + *the brain wires itself.* Every page write extracts entity references and creates typed relationships (`attended`, `works_at`, `invested_in`, `founded`, `advises`) **with zero LLM calls**, then appends a Timeline entry. Read-Enrich-Write cycle per inbound signal. No batch consolidation step.

This is the central trade-off. gbrain pays per-write to keep the graph live; llm-wiki batches and accepts lag. gbrain's zero-LLM link extraction (regex / NER on the markdown body) is genuinely cheap — it doesn't require the DB to work, only the typed-relation vocabulary.

### 2. Page anatomy

- **gbrain:** *"Two-layer pages"* — **State** above the `---` (executive summary, current structured fields, "Open Threads", "See Also"), **Timeline** below (append-only, reverse-chronological, dated, sourced). Plus `people/.raw/<slug>.json` sidecar with timestamped API responses.
- **llm-wiki:** atomic Markdown articles, one concept per file, wikilinks into substrate. No per-entity Timeline layer, no JSON sidecar. `knowledge/` subfolders form the type axis (concepts / connections / projects / people / qa / facts).

llm-wiki's atomic-articles pattern works well for `concepts/` and `qa/`. It under-aggregates for `people/` and `projects/` — there's no place where "everything I know about Jane Doe" gets compiled. State+Timeline is the natural fit for entity folders.

### 3. Taxonomy breadth

- **gbrain:** 19+ MECE directories — people / companies / deals / meetings / projects / ideas / concepts / writing / programs / org / civic / media / personal / household / hiring / sources / prompts / inbox / archive. Each folder needs a `README.md` resolver; `RESOLVER.md` is a master decision tree. *"Read RESOLVER.md before creating any page."*
- **llm-wiki:** 6 types + facts. Narrower, more uniform, less domain-specific.

gbrain's breadth reflects Garry's world (VC / civic / hiring / household). The pattern that transfers cleanly is **per-folder RESOLVER doc**, not the wide taxonomy.

### 4. Facts vs. Takes (gbrain's epistemological split)

- **gbrain:** **Facts** (hot storage, owner-stated — events / preferences / commitments / beliefs) ≠ **Takes** (cold storage, *"WHO believes WHAT with confidence + time"*, attributed across all speakers, scales to 100K+ rows). Dream-Cycle promotes Facts→Takes via overnight synthesis. *"Never dump takes into the facts table."*
- **llm-wiki:** only Hard-Facts (operator-owned, `trust: confirmed|asserted|provisional` + `sources:`). Third-party belief attribution has no slot.

Takes is a category that doesn't exist in llm-wiki. `daily/` captures quotes; `concepts/` distills ideas; but "Person X believes Y at confidence Z, source daily/2026-04-12" has no home. Worth its own backlog candidate.

### 5. Two-axis routing (Brain × Source)

- **gbrain:** **Brain** (database owner) × **Source** (named content repo *within* that DB). 6-tier resolution: explicit flag → env → dotfile → path-prefix mount → config-default → fallback. Team brains mountable.
- **llm-wiki:** one vault, one engine instance. Multi-vault is an open question since M001 ("does the engine index multiple Obsidian vaults, or merge-then-ingest?").

gbrain's split is well-thought-out but solves a problem (team data sharing, multi-tenant) that llm-wiki has not committed to. Worth re-reading when multi-vault becomes concrete.

### 6. "Thin harness, fat skills"

- **gbrain:** ~200-line harness + 50 markdown skills. *"Intelligence lives in markdown skill documents, not the runtime."* Skills carry architecture diagrams, routing trees, judgment calls, failure modes. Distributable as recipes.
- **llm-wiki:** engine code IS the harness (`compile.py`, `flush.py`, `lint.py`, …). 5 skills are auxiliary (engine-pr, vault-triage, ingest-audio).

Different load-bearing bet. gbrain's pattern works because OpenClaw/Hermes exists as a runtime platform that *executes* skills. llm-wiki has no such platform; skills are Claude Code helpers, not the execution surface.

### 7. Determinism routing (Minions vs. Sub-agents)

- **gbrain:** formalized — *"Deterministic (same input → same steps → same output) → Minions. Judgment (input requires assessment) → Sub-agents."* Encoded in `src/core/minions/`.
- **llm-wiki:** implicit (Python script vs. Claude Agent SDK call). Already aligned in practice (feedback memory: "no agent for deterministic actions") but not formalized.

### 8. Trust boundary

- **gbrain:** `OperationContext.remote: true|false` is **TypeScript-required** since v0.26.9. Security-sensitive operations enforce stricter filesystem confinement when `remote === true`.
- **llm-wiki:** no equivalent (local-only assumption).

Relevant only if llm-wiki ever exposes engine ops to external agents. Currently not on the table.

### 9. Side loops

- **gbrain:** **Dream Cycle** (overnight transcript synthesis → Reflections), signal-detector (entity extraction on intake), zero-LLM auto-link extraction.
- **llm-wiki:** Curiosity loop (producer alive, consumer missing — drift #1), Suggestions (YAML + per-action approval), `optimize-claude-md` piggyback.

Dream-Cycle is the cleanest portable pattern: scheduled cross-time synthesis pass that produces new `knowledge/` content from recent `daily/` + transcripts. Different from compile (per-file distillation) — synthesizes *across* the timeline.

## What llm-wiki could adopt — three concrete patterns

High-value, low implementation cost, no DB tax. Each gets its own backlog candidate:

1. **State+Timeline page anatomy for entity folders** — `.ytstack/backlog/entity-pages-state-timeline.md`
2. **Takes substrate** — `.ytstack/backlog/takes-substrate.md`
3. **Dream-Cycle scheduled synthesis** — `.ytstack/backlog/dream-cycle.md`

Additional smaller items not yet broken out:

- **Per-folder RESOLVER.md** in each `knowledge/<typ>/` — explicit "what belongs here / what doesn't". Reduces the LLM's filing decision during compile. Lint extension: warn on articles that don't match the resolver. Lift: 1 day, 6 README files + 1 lint check.
- **JSON sidecar pattern** for entity pages — `knowledge/people/jane-doe.md` + `knowledge/people/.raw/jane-doe.json` with structured fields (aliases, contacts, last-seen-in-meeting-id, …). Tension with the "Single format when one consumer" feedback rule — only justified if a second consumer (Dataview / Bases / dashboard chart) actually emerges.
- **`wiki doctor` with verify protocol** — extends `scripts/health.py`. 7-step check: schema-verify, embedding-dim-check (if local embeddings ever land), orphan/dangling audit, eval-replay against held-out queries. Anchor for the eval-bench point below.
- **IR-style eval bench** — held-out query set with expected article hits. `evals/queries.jsonl` + replay script measuring P@5 / R@5. Makes "compile quality improved" measurable instead of anecdotal. Especially relevant for the upcoming Jamie-distillation probe (do summaries become useful person/project pages, or just denser substrate?).

## What llm-wiki should NOT adopt

1. **Postgres / pgvector dependency.** Breaks engine-vault-split, breaks "Obsidian reads everything", introduces ops surface. llm-wiki's bet is markdown-as-substrate is enough below ~1K articles; a DB is a different project.
2. **Hybrid retrieval (vector + keyword + RRF).** Only justified above gbrain's own PGLite→Supabase threshold. lxw is at ~668 nodes.
3. **TypeScript/bun rewrite.** Sunk-cost-driven, no architectural gain.
4. **Wide VC taxonomy** (`deals/`, `civic/`, `hiring/`, `household/`, `programs/`, `org/`, `media/`). Operator-specific to Garry's world. Keep llm-wiki taxonomy narrow; extend on demand.
5. **34 skills as distributable recipes.** Works for gbrain because OpenClaw is a distribution platform. llm-wiki has no equivalent; skills stay auxiliary.

## Where llm-wiki has the stronger argument

1. **No DB tax** — Obsidian + grep + Dataview is enough under ~1K articles. The "everything is a file" invariant survives intact.
2. **Multi-agent hooks** — gbrain has MCP, but nothing comparable to the SessionStart / SessionEnd / PreCompact wiring across four agents (Claude / Codex / Gemini / Cursor).
3. **Engine/vault split as a disk invariant** — gbrain mixes brain + DB + code; backup hygiene is worse. llm-wiki's `<vault>/.wiki/` rule means vault backups never accidentally include engine state.
4. **Operator-owned facts override LLM-emitted content** — `wiki correct` with trust tiers + required sources is more disciplined than gbrain's "human always wins" assertion, which doesn't have the same provenance surface.

## Verdict

gbrain is **Personal-KB-as-database-with-agent-loop** for someone with 4K+ people pages and 21 cron jobs running. llm-wiki is **Personal-KB-as-distilled-markdown** for someone whose wiki must be Obsidian-native and LLM-distilled without a server. Same need, near-inverted trade-offs.

The three transferable patterns (State+Timeline / Takes / Dream-Cycle) share an axis: **per-entity, time-aware, attribution-aware**. Implemented as a bundle they form an "entity-pages layer" that complements the existing atomic-articles pattern without replacing it. Implemented separately they're individually weaker.

Backlog-tracked as three siblings until one becomes load-bearing (e.g. Jamie-meeting attendees accumulating without a people-page aggregation surface).

## Sources

- gbrain README, AGENTS.md, CLAUDE.md (verbatim quotes above)
- `docs/ENGINES.md` — PGLite vs Postgres split
- `docs/GBRAIN_RECOMMENDED_SCHEMA.md` — 19-folder MECE taxonomy + State+Timeline template
- `docs/ethos/THIN_HARNESS_FAT_SKILLS.md` — design philosophy
- `docs/ethos/MARKDOWN_SKILLS_AS_RECIPES.md` — distribution model
- `docs/architecture/brains-and-sources.md` — two-axis routing
- `docs/takes-vs-facts.md` — epistemological split
- `skills/brain-ops/SKILL.md` — brain-first-lookup contract
- Repo: `github.com/garrytan/gbrain` @ master, fetched 2026-05-13
