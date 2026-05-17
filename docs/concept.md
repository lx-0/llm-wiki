# Concept

An LLM Wiki implementation that turns scattered personal data into a compiled, queryable knowledge base. Inspired by [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [Cole Medin's claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler).

## Contents

- [The problem](#the-problem) — what scattering looks like and why naive ingest fails
- [Core idea](#core-idea) — compile once, read every day
- [Architecture: three layers](#architecture-three-layers) — Working Memory · optional Vector RAG · Sources of Truth
- [Data flow](#data-flow) — substrates → compile → wiki
- [Compile — not retrieve](#compile--not-retrieve) — why this isn't RAG
- [Cognitive functions](#cognitive-functions) — perception, memory, attention as system roles
- [Curiosity loop](#curiosity-loop) — gap detection that queues the next compile
- [Optimization suggestions](#optimization-suggestions) — YAML proposals with per-action approval
- [Personal tasks](#personal-tasks) — operator commitments extracted into entity pages (M005)
- [Design rationale](#design-rationale) — the hard trade-offs

## The problem

Personal knowledge ends up scattered across:

- A code/projects directory (sources, repos, assets)
- A screenshots dir (visual evidence of daily thinking)
- A downloads dir (research artefacts, drift)
- An Obsidian or other notes vault (curated, but small)
- Cloud drives, email, calendars, browser history

Three failure modes follow:

1. **Knowledge loss** — files are artefacts of thought, but without context they're inert. A screenshot from three months ago might capture a product idea, but nobody remembers.
2. **Duplicates** — the same PDF lives in three folders. Naïve ingest creates chaos.
3. **Scale** — hundreds of GB don't fit in a vault. They shouldn't.

## Core idea

**Compile once. Read every day.**

Personal knowledge that stays scattered is illegible. Personal knowledge that gets aggressively centralized is unmaintainable. llm-wiki splits the difference: a small, opinionated set of substrates feeds a Claude-Agent-SDK compile pass that turns them into atomic, cross-linked Markdown articles. The compiled wiki is the working surface — read by you and by every agent that touches your vault. The substrates underneath are immutable; only the compile output is allowed to evolve.

Mixed reality on the storage side: some sources are referenced (mailbox, calendar, browser data live in their canonical apps; collectors only write metadata into `raw/notes/`); others are owned (web clippings, audio recordings, meeting transcripts, PDFs — copies live in `raw/articles/`, `raw/audio/`, `raw/transcripts/`, `raw/papers/` because their canonical home is unstable or non-existent). The wiki layer (`knowledge/`) is purely derivative — wikilinks and prose, never originals.

```text
Working memory   = vault (Obsidian root)    you read & edit here
Knowledge        = compiled wiki (knowledge/)  LLM writes here
Long-term recall = optional vector RAG (L2)    deep semantic search
Senses           = collectors (email, jamie, gmeet, voice, calendar, browser, screenshots, youtube, NAS, …)
Body             = filesystem, drives, APIs
```

## Architecture: three layers

### L1 — Working Memory (Obsidian Vault)

Two vaults, two purposes:

- **Personal vault** — PARA-structured, hand-curated. Active projects, areas, decisions, agent briefings. Hundreds of files, manually organized.
- **Wiki vault** — implements Karpathy's `raw/` + Cole's `claude-memory-compiler` pattern. Auto-compiled knowledge from all sources.

The compiler reads `raw/` (memories, mail metadata, calendar events, browser history, screenshots, …) and compiles to `knowledge/` (concepts, connections, projects, people, qa). The LLM decides what's worth knowing and surfaces cross-source links.

**Storage rules** (the project's actual stance, not Karpathy's stricter version):

- **Code repos and OS-managed media never enter L1.** Code stays in `~/Code/`, screenshots stay in `~/Screenshots/`, browser data stays in profile dirs. Reference notes only (`→ see ~/Code/<repo>`).
- **Mailbox / calendar bodies never enter L1** — collectors write metadata to `raw/notes/` only.
- **Things without a stable canonical home DO enter L1.** Web clippings (`raw/articles/*.html`), audio you record (`raw/audio/`), papers (`raw/papers/`), meeting transcripts (`raw/transcripts/`). The compromise is deliberate: these substrates need ownership, and storing the original is what guarantees the compile pass is reproducible.
- **Vault size budget is loose.** Karpathy's gist suggests <100 MB; in practice this engine handles a few GB across `raw/audio/` + `raw/papers/` without trouble. The hard bound is "Obsidian still indexes responsively."

### L2 — Optional Vector RAG (deep search)

When the wiki grows past ~500 articles and `index.md` exceeds comfortable context:

- Vector store with semantic search
- Two scopes: `private:user` and `tenant:org`
- Results can be ingested as new sources if they contain new info

This layer is optional. Most queries should be answered from L1 alone.

### L3 — Sources of Truth (raw data)

Files stay in their canonical location:

- Code in the projects directory
- Screenshots in the OS screenshot folder
- Email in IMAP / Gmail
- Calendar in CalDAV / iCal / Google
- Browser data in profile dirs
- Cloud drives, NAS

Collectors scan L3 → write metadata to `raw/notes/` → the compiler turns it into wiki articles.

## Data flow

```text
Collectors                   Curated sources       Daily rollup (per-day)
(email, jamie, gmeet, voice, (raw/articles,        (daily/<date>/sessions.md
 health + calendar, browser,  raw/papers,           by session-hook;
 tabs, screenshots, youtube   raw/notes,            health/meetings/voice/email
 — all Registry-discovered)   raw/transcripts)      by collectors; daily/<date>.md
                                                    digest by compile-stage)
       │                          │                     │
       │                          │                     │
       ▼                          ▼                     ▼
                ┌──────────────────┐
                │       raw/       │  ← immutable; LLM reads, never writes
                └──────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │    compile.py    │  ← Claude Agent SDK
                │  (Karpathy +     │     reads index.md + AGENTS.md
                │   Cole's engine) │     uses Read/Grep/Glob to fetch detail
                └──────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │   knowledge/     │  ← LLM owns; user reads
                │  concepts/       │
                │  connections/    │  ← cross-source links
                │  projects/       │
                │  people/         │
                │  qa/             │
                │  index.md        │  ← master catalogue
                │  log.md          │  ← operations log
                └──────────────────┘
```

## Compile — not retrieve

The defining choice: **compile once, query fast**, instead of retrieving on every query (RAG).

| Approach | Cost per query | Latency | Cross-doc reasoning | Caveat |
|---|---|---|---|---|
| RAG | re-embed + retrieve every time | seconds | weak (chunks isolated) | scales linearly with query count |
| Wiki | one-time compile per source | ms (it's already markdown) | strong (LLM saw all sources during compile) | bound by index size |

The compiler runs once per new source (~$0.01–0.05 per source). One source typically updates 5–15 wiki articles. Querying is then a Markdown read — no vector search.

## Cognitive functions

The system has the same shape as memory in cognition:

| Function | Implementation |
|---|---|
| **Sensory buffer** | session-end hook captures the live conversation transcript |
| **Episodic memory** | `daily/<date>/` — per-day, per-source captures (sessions / health / meetings / voice / email). Compile-stage `daily-digest` agent produces a `daily/<date>.md` distillation across all sources. |
| **Consolidation** | `compile.py` distills episodic + curated sources into structured wiki |
| **Semantic memory** | `knowledge/` — atomic concepts, connections, projects, people |
| **Working memory** | `session-start` hook injects a pointer block (paths to `index.md`, `knowledge/`, `raw/`, `AGENTS.md`) + recent daily-log tail; the agent pulls articles on demand via Read/Grep |
| **Retrieval** | `query.py` walks the wiki, optionally writes answers back as Q&A |
| **Self-healing** | `lint.py` — orphan detection, stale frontmatter, broken links, contradictions |
| **Curiosity** | post-compile gap detection → deep-scan requests → next compile fills the gap |

## Curiosity loop

After each compile, a small local LLM (Ollama, free) inspects the new article + index and identifies gaps. It writes JSON requests to `raw/requests/`. A consumer (`wiki curiosity`, also wired as a 24h piggyback) picks the oldest pending request, dispatches it to the matching backend (`scripts/curiosity/backends/<type>.py`), and writes the deep-scan output into `raw/notes/`. The next compile distills it into knowledge.

Today there's one backend: `email-deep-scan`. It reads the request's account + folder, calls `scan_deep` on the Mailbox adapter (Thunderbird mbox, Gmail API, or All-Inkl IMAP), and writes a markdown report with full bodies into `raw/notes/email/deep-{slug}.md`. Future request types (e.g. `youtube-deep-watch`, `jamie-followup`) plug in as additional backend modules without touching the producer or the CLI.

```text
compile.py → curiosity model → raw/requests/*.json
       ↓ (piggyback, 24h cooldown)
deep-scan → raw/notes/<source>/deep-*.md
       ↓
compile.py (next cycle) — gap closed
```

The curiosity model uses a full JSON Schema with `enum` constraints (not just `format: "json"` — that's not enough; the model invents field names).

## Optimization suggestions

The compiler can also generate **action proposals** — e.g., "this folder receives 80% newsletter mail; consider an auto-filter rule." Each suggestion is a YAML file in `raw/suggestions/`, with per-action approval. An interactive executor (`suggestions/cli.py`) walks the YAML, prompts for approve / reject / dry-run per action, and dispatches approved ones to a backend (`suggestions/backends/imap.py` for IMAP move/tag/set-flags actions; future backends plug in alongside).

The producer is a small subsystem (`suggestions/producer.py`) called from `compile.py` whenever an email source is processed. The pattern generalizes beyond email — anywhere the compiler spots a repeatable manual action, it can propose automation under the same producer-executor-backend split.

## Personal tasks

The compiled wiki is a knowledge base, but personal data also carries **commitments** — "I'll send the deck by Friday", "waiting on Bob's intro", decisions to follow up on. Karpathy's and Cole Medin's concepts both scope themselves to reference content only; tasks are out. gbrain (Garry Tan's production-tested 15.4K-star LLM-wiki) made the opposite call: `commitment` is a Fact-kind, embedded in entity pages as `## Action Items` + `## Open Threads` sections. llm-wiki took that path in **M005**: tasks live **inside** `knowledge/people/<slug>.md` and `knowledge/projects/<slug>.md`, **not** in a separate top-level folder.

The mechanics:

- **Two-layer page shape** for `type: person|project`. Compiled-truth State block above `---` (executive summary, structured fields, `## Action Items` in Obsidian-Tasks-plugin syntax — `- [ ]` + `📅 YYYY-MM-DD` + `⏫` + `🔁`, `## Open Threads` as prose bullets, free-prose body, `## See also`), append-only `## Timeline` below. Atomic shape stays for `concept | connection | qa | moc | fact`. Compile prompt branches on `type:`.
- **Extraction.** `compile.py` reads jamie/gmeet transcripts (and email when the substrate has explicit commitments), identifies the **Task / Owner / Deadline / Context** quartet, slugifies owners (`Jane Doe` → `jane-doe`), looks up existing entity pages (index grep + aliases-frontmatter grep), creates stubs for new owners, routes commitments to the owner's `## Action Items`, blocked items to `## Open Threads`, and adds a Timeline citation on every entity page touched.
- **Lifecycle.** Each compile pass reads existing State before rewriting. Unresolved items carry forward unchanged. Manual `- [x]` (operator-checked) is preserved across re-runs. When new substrate provides resolution evidence ("sent the deck", "Bob and I synced"), the matching item demotes to a Timeline entry marked `[resolved]`.
- **Lint** enforces the shape: `check_two_layer_pages` (State + `---` + Timeline + reverse-chronological order), `check_action_item_syntax` (Obsidian-Tasks-plugin syntax validity).
- **Surface.** The Obsidian dashboard's `## 📌 Personal Tasks (Wiki)` pane shows Overdue / Today / This week / No-due-date queries. The `knowledge/MOCs/inbox-tasks.md` MOC is the full cross-entity inbox. A `📌 Open commitments: N across M entities` stat card sits next to the engine pipeline status.

LLM-emission quality cannot be CI-tested. The plumbing (prompt rules + lint + fixtures) is CI-covered; real extraction quality lives in `docs/m005-s03-canary-procedure.md` — three canaries (synthetic fixture → live jamie → live gmeet) with grep verification and pass/fail/caveat decisions.

## Operator self-reports (analytical surface)

The knowledge wiki captures what the operator **knows** and **owes**. A separate analytical surface — `<vault>/reports/` — captures what the substrate **shows** about the operator: validated psychometric screens (PHQ-9 depression, GAD-7 anxiety, WHO-5 wellbeing, PSS-10 stress, ISI insomnia, OLBI burnout — plus K6 + ASRS-v1.1 available off-manifest) scored by an informant agent reading the operator's own daily / raw / health substrate. Self-cartography: turn the substrate into a longitudinal portrait.

**The key inversion.** These are not self-administered questionnaires. They are **Informant Reports** — an outside observer (the LLM) reads what the operator wrote, did, and felt across the lookback window, then answers the validated instrument's items on the operator's behalf. Items the substrate cannot answer (interior states with no behavioural fingerprint, e.g. PHQ-9 Q9 suicidal ideation) carry `substrate_inferable: false` and can only be filled in by the operator via `wiki study answer`. The LLM never guesses them.

**Why this is not the compile pipeline.** The reports surface is structurally air-gapped: engine code lives under `scripts/reports/_engine/` (not `scripts/`), output lives in `<vault>/reports/` (not `knowledge/`), and `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES` keeps `reports/` invisible to `compile.py`. Reports are not knowledge — they are measurements of the knowledge-producing operator. Mixing them would corrupt both.

**Determinism + LLM blended.** Scoring is pure-Python (Likert + reverse-coding + cutoffs from published norms). The LLM is restricted to filling in raw item answers from substrate evidence. Each per-instrument report includes the instrument source, the citation, the scoring formula, the substrate sources used, and the coverage percentage (Q6 future-fit posture — every report is self-explaining).

**Two-pass analyst.** Pass-1 fires inside `wiki study run` after the run succeeds: a Read+Grep-scope-locked agent writes `_analysis.md` next to `_summary.md` in the same run dir. Pass-2 runs on demand via `wiki analyze`: synthesises across all studies into `reports/analyses/<UTC-ts>.md`. Both passes use the same scope-lock pattern as inference (`make_path_scope_gate([])` — no writes anywhere).

**Charts.** Cross-instrument radar, coverage sparkline, per-instrument item-level radar with axis legend, per-instrument timeline — all pure-Python SVG (no matplotlib), embedded side-by-side via HTML flex in `_summary.md`. Stale charts auto-prune when an instrument is dropped from the manifest.

## Design rationale

See [.ytstack/KNOWLEDGE.md](../.ytstack/KNOWLEDGE.md) for the hard-won learnings: Ollama gotchas, rate-limit debugging, why Karpathy/Cole's flush-context pattern is wrong for agentic workflows, why we use file-per-memory instead of bundles, why SMB beats SSH for NAS access.
