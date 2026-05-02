# Concept

An LLM Wiki implementation that turns scattered personal data into a compiled, queryable knowledge base. Inspired by [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [Cole Medin's claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler).

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

Mixed reality on the storage side: some sources are referenced (mailbox, calendar, browser data live in their canonical apps; collectors only write metadata into `raw/notes/`); others are owned (web clippings, audio recordings, agent-memory snapshots, PDFs — copies live in `raw/articles/`, `raw/audio/`, `raw/memories/`, `raw/papers/` because their canonical home is unstable or non-existent). The wiki layer (`knowledge/`) is purely derivative — wikilinks and prose, never originals.

```text
Working memory   = vault (Obsidian root)    you read & edit here
Knowledge        = compiled wiki (knowledge/)  LLM writes here
Long-term recall = optional vector RAG (L2)    deep semantic search
Senses           = collectors (email, calendar, browser, screenshots, NAS, …)
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
- **Things without a stable canonical home DO enter L1.** Web clippings (`raw/articles/*.html`), audio you record (`raw/audio/`), papers (`raw/papers/`), agent-memory snapshots (`raw/memories/`), Whisper transcripts (`raw/transcripts/`). The compromise is deliberate: these substrates need ownership, and storing the original is what guarantees the compile pass is reproducible.
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
Collectors        Curated sources       Sessions
(scan-email,      (raw/articles,        (daily/, auto-captured
 scan-calendar,    raw/papers,           via session-end hook)
 scan-browser,     raw/notes,
 scan-screenshots, raw/transcripts)
 scan-nas)             │                     │
       │               │                     │
       ▼               ▼                     ▼
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
| **Episodic memory** | `daily/` — chronological session logs (what happened, when) |
| **Consolidation** | `compile.py` distills episodic + curated sources into structured wiki |
| **Semantic memory** | `knowledge/` — atomic concepts, connections, projects, people |
| **Working memory** | `session-start` hook injects `index.md` into next session's context |
| **Retrieval** | `query.py` walks the wiki, optionally writes answers back as Q&A |
| **Self-healing** | `lint.py` — orphan detection, stale frontmatter, broken links, contradictions |
| **Curiosity** | post-compile gap detection → deep-scan requests → next compile fills the gap |

## Curiosity loop

After each compile, a small local LLM (Ollama, free) inspects the new article + index and identifies gaps. It writes JSON requests to `raw/requests/`. A piggyback task picks up the oldest pending request and runs a deep scan (e.g. read full email bodies in a specific folder, reconstruct threads, filter via LLM). The deep-scan output lands in `raw/notes/` and gets compiled in the next cycle.

```text
compile.py → curiosity model → raw/requests/*.json
       ↓ (piggyback, 24h cooldown)
deep-scan → raw/notes/<source>/deep-*.md
       ↓
compile.py (next cycle) — gap closed
```

The curiosity model uses a full JSON Schema with `enum` constraints (not just `format: "json"` — that's not enough; the model invents field names).

## Optimization suggestions

The compiler can also generate **action proposals** — e.g., "this folder receives 80% newsletter mail; consider an auto-filter rule." Each suggestion is a YAML file in `raw/suggestions/`, with per-action approval. A separate executor script applies approved actions.

The pattern generalizes beyond email — anywhere the compiler spots a repeatable manual action, it can propose automation.

## Design rationale

See [.ytstack/KNOWLEDGE.md](../.ytstack/KNOWLEDGE.md) for the hard-won learnings: Ollama gotchas, rate-limit debugging, why Karpathy/Cole's flush-context pattern is wrong for agentic workflows, why we use file-per-memory instead of bundles, why SMB beats SSH for NAS access.
