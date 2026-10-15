# Karpathy LLM Wiki vs. Naive PKM — Architecture Analysis

A comparison of Karpathy's LLM Wiki pattern against a typical "naive" personal knowledge management (PKM) setup (Obsidian + Dataview + plugins + manual triage). Useful before adopting this implementation, especially if you're migrating from a folder-and-tags vault.

## Karpathy's core architecture

```text
Raw sources (immutable)  →  Wiki (LLM-written)  →  Schema (AGENTS.md / CLAUDE.md)
   ↑ human curates           ↑ LLM owns             ↑ co-evolves
```

Three operations: **ingest**, **query**, **lint**.
Two navigation files: **index.md** (catalogue) and **log.md** (chronological).
One principle: **compile, don't retrieve.**

## Fundamental differences

### 1. Philosophy: who does the work?

| | Karpathy LLM Wiki | Naive PKM |
|---|---|---|
| **Human** | Curates sources, asks questions, thinks | Organises folders, moves files, triages inbox |
| **LLM** | Writes ALL wiki pages, maintains cross-links, keeps everything current | Transcribes, suggests folders, waits for approval |
| **Result** | Human thinks, LLM works | Human works, LLM assists |

> *"The tedious part of maintaining a knowledge base isn't reading or thinking — it's the bookkeeping. Humans abandon wikis because the maintenance burden grows faster than the value."*

Many PKM systems unwittingly maximise the bookkeeping burden (PARA folders, triage workflows, approval steps). The LLM Wiki pattern minimises it.

### 2. Compile vs. retrieve

| | Compile-time (Karpathy) | Retrieve-time (RAG / naive PKM) |
|---|---|---|
| **Approach** | Knowledge is compiled to wiki pages **once**. Cross-links are pre-baked. Contradictions are pre-flagged. | Knowledge is reassembled on every query (vector search, BM25, Dataview). |
| **Result** | Compiled knowledge grows and gets richer. Each new source improves 10–15 existing pages. | Index grows; knowledge stays fragmented in chunks. No synthesis. |
| **Analogy** | Compiler: source → binary (once, persistent) | Interpreter: source → execution (every time, fresh) |

This is the biggest single difference. In Karpathy's pattern, adding a source updates entity pages, topic pages, the index, flags contradictions, and adds cross-links. In a naive setup, adding a source produces one note in an inbox.

### 3. Source separation

| | Karpathy | Naive PKM |
|---|---|---|
| **Raw sources** | Their own folder, **immutable**. LLM reads, never writes. | Mixed with notes in the same vault. |
| **Wiki** | Its own folder, **fully LLM-owned**. Human reads, never writes. | Human and agent both write, intermixed. |
| **Boundary** | Clear: source-of-truth ≠ artefact | Unclear: is this note a source or a synthesis? |

A clean data pipeline (input → processing → output) beats a vault where everything is simultaneously input and output.

### 4. Complexity

| | Karpathy | Naive PKM |
|---|---|---|
| **Infrastructure** | Markdown files + git. Optional: vector store for L2. | Vault + Dataview + QuickAdd + Buttons + Homepage + CSS snippets + RAG service + scheduled jobs + MCP servers |
| **Setup** | "Share this gist with your LLM and work together" | 6+ plugins, YAML configs, scheduled routines, API keys |
| **Maintenance** | LLM does the upkeep; schema co-evolves. | Human pegs plugins, debugs buttons, tweaks queries. |

Naive PKM tends to be a complex system that needs the human to function. The LLM Wiki is a simple system that needs the LLM to function. The latter scales better with the human's actual time budget.

### 5. Knowledge compounding

| | Karpathy | Naive PKM |
|---|---|---|
| **Query results** | Good answers become new wiki pages. Knowledge grows through questions. | Answers vanish into chat history. |
| **Ingest** | 1 source → 10–15 pages updated | 1 audio → 1 transcript note; no cross-effects |
| **Over time** | Wiki gets exponentially more valuable | Vault gets linearly larger |

### 6. Lint

| | Karpathy | Naive PKM |
|---|---|---|
| **Health check** | Periodic: contradictions, orphan pages, missing cross-links, stale claims, gaps | Usually absent |
| **Self-improvement** | LLM proposes new questions and sources | Manual |

### 7. Schema as operating manual

| | Karpathy | Naive PKM |
|---|---|---|
| **Schema role** | `AGENTS.md` / `CLAUDE.md` is **operating instructions**: how do you ingest? how do you query? what page types exist? what conventions apply? | Navigation aid: folder structure, frontmatter format, plugin list. |
| **Co-evolution** | Schema evolves with the wiki. LLM + human update conventions together. | Schema is updated manually when structure changes. |

### 8. Ingest model

| | Karpathy | Naive PKM |
|---|---|---|
| **Flow** | Drop source → LLM reads → discuss key takeaways with human → summary page → index update → entity pages update → topic pages update → log entry | Drop file → transcribe → note in inbox → manual triage → move to folder |
| **Depth** | One source touches 10–15 pages | One source produces 1 note |
| **Interaction** | LLM discusses the source | LLM asks "where do I file this?" |

### 9. Navigation

| | Karpathy | Naive PKM |
|---|---|---|
| **index.md** | Content catalogue: every page with link, summary, metadata. LLM reads index first. | Dashboard: auto-generated lists; no summaries. |
| **log.md** | Chronological append-only log of all operations | Local triage logs (only triage decisions, not vault-wide). |
| **Graph** | Obsidian Graph View over compiled pages — dense, meaningful | Obsidian Graph View over loose notes — barely connected |

### 10. Human-in-the-loop

| | Karpathy | Naive PKM |
|---|---|---|
| **Approval** | Optional. Human reads along, corrects when needed. | Mandatory. Nothing happens without approval. |
| **Trust** | LLM is treated as a competent wiki author. | LLM is an assistant that needs sign-off. |

## What Karpathy does better

1. **Lets the LLM do the work** — not the human.
2. **Compilation over retrieval** — knowledge synthesised once, not searched every time.
3. **Radically simple** — markdown + git; no plugin hell.
4. **Every interaction enriches the system** — queries become pages; sources update many pages.
5. **Clean separation** — sources (immutable) vs. wiki (LLM-written) vs. schema (operating manual).
6. **Self-healing** — lint operation finds and fixes problems.
7. **Schema as runbook** — not just documentation, but operating instructions for the LLM.

## What this implementation adds on top

- **Multi-source collectors** (email, calendar, browser, screenshots, NAS, …) feeding `raw/notes/`.
- **Curiosity loop** — post-compile gap detection, deep-scan requests, next-cycle gap closure.
- **Optimization suggestions** — compiler proposes mutations to source systems (filter rules, IMAP moves), per-action human approval, separate executor.
- **Session capture** — auto-flush every Claude Code / Codex / Gemini session into `daily/` so chat work compounds.
- **Audio ingest** — Whisper-based transcription pipeline.

## What to change if migrating from naive PKM

1. **Re-frame the vault: it's a wiki, not a filesystem.** The LLM compiles knowledge into pages — entity pages, topic pages, syntheses. The human stops organising folders.
2. **Separate raw sources.** Own `raw/` directory, immutable. Wiki pages in `knowledge/`. Clear pipeline.
3. **Ingest = compilation.** A new source doesn't produce 1 note; it updates 10+ pages. The LLM discusses key takeaways before compiling.
4. **Persist query results.** Good answers become Q&A pages. Knowledge compounds.
5. **Add lint.** Periodic health checks: contradictions, gaps, orphans.
6. **Make the schema operational.** Not "here is the structure" but "this is how you work with this wiki."
7. **Reduce plugin complexity.** Fewer buttons, less Dataview, more LLM-written pages.
8. **Loosen approval.** LLM writes wiki pages directly. Only sources need explicit human curation.
