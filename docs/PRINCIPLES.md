# Core principles

The ten rules that define how this wiki behaves — its constitution. Each is stated
as an imperative, grouped by where it sits in the pipeline (intake → source →
authorship → mechanic → structure → isolation → lifecycle → integrity → scope), and
attributed to its source.

Most come straight from [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
and [Cole Medin's claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler);
a few are this project's own, and one is informed by [OpenClaw's wiki plugin](https://docs.openclaw.ai/cli/wiki).
Where a rule is **ours**, that is called out — we don't borrow authority we don't have.

> **Quote provenance.** Karpathy quotes below are extracted from his public gist; verify
> against the source before relying on exact wording. "Ours" quotes are from this repo's
> `concept.md` / `AGENTS.md` / `.ytstack/DECISIONS.md`.

---

## 1 · Intake — collect for coverage, not yield

**Ingest for persona-coverage, not signal-density.**

This is a *self*-cartography engine: the target is a complete portrait of the operator,
not maximum knowledge-per-source. A low-yield channel that covers an otherwise-dark
side of the person (what they read for leisure, how they sleep, what they're curious
about) can outrank a high-yield source redundant with what's already ingested.

> "Value a candidate substrate/collector by persona-coverage, not signal-density per
> row. This is a self-cartography engine: it optimizes for completeness-of-portrait,
> not knowledge-yield." — **ours** (`AGENTS.md`; `.ytstack/DECISIONS.md` 2026-05-22)

## 2 · Source — never change the originals

**The source (`raw/`) is immutable — the LLM reads it, never writes it.**

The raw material is the ground truth of what actually happened. Compilation reads from
it but never edits or deletes it. (Engine-owned mirrors that a collector prunes on its
own lifecycle are the one nuance — that's lifecycle pruning by the owner, not content
mutation.)

> "These are immutable — the LLM reads from them but never modifies them." — **Karpathy**

## 3 · Authorship — the LLM writes; you direct

**The LLM authors the wiki; you curate sources and ask questions — you don't hand-maintain it.**

The wiki is continuously LLM-written and LLM-maintained. The human's job is sourcing
and direction, not filing and bookkeeping. Hand-editing a compiled article is the rare
exception, not the workflow.

> "You never (or rarely) write the wiki yourself — the LLM writes and maintains all of it."
> "The human's job is to curate sources, direct the analysis, ask good questions, and
> think about what it all means." — **Karpathy**

## 4 · Authorship — mutations go through sanctioned channels

**Changes land through defined, structured channels — never freeform surgery on a compiled page.**

Every change to `knowledge/` goes through a sanctioned path: a recompile, a hard fact,
the dream-cycle, or a narrow structured update into a managed section. No manual prose
surgery on finished pages — that's what keeps articles consistent, reversible, and safe
to let agents touch. Applies to agents too.

> "Use `wiki apply` instead of hand-editing managed generated sections." — **OpenClaw**
> (this project's analogue: sentinel-managed regions + "the CLI is the only sanctioned
> write path", `use-llm-wiki` skill)

## 5 · Mechanic — compile, don't retrieve

**Distill each source once into durable Markdown; don't re-search the raw files at query time.**

The defining choice. The system does the cross-referencing work once, at compile time,
and saves the result as plain Markdown. A query is then a Markdown read — no embedding,
no per-query retrieval. (*"compile, don't retrieve"* is our shorthand for Karpathy's idea.)

> "Instead of just retrieving from raw documents at query time, the LLM incrementally
> builds and maintains a persistent wiki" — **Karpathy**

## 6 · Structure — flat, atomic, index-navigated

**Keep it flat and atomic; navigate by `index.md`; minimize bookkeeping.**

No deep folder hierarchies — pages are small and single-topic, organized by article
*type*, tied together by one catalog (`index.md`). A chronological operations record
lives outside the vault at `.wiki/logs/operations.md` so it can grow without dragging
Obsidian's index along. Deep filing systems die because the maintenance burden outgrows
the value; flat + LLM-maintained index avoids that.

> "The wiki is just a git repo of markdown files." "index.md … a catalog of everything
> in the wiki — each page listed with a link, a one-line summary, and optionally
> metadata." "log.md is chronological … an append-only record of what happened and when
> — ingests, queries, lint passes." — **Karpathy** (this engine keeps the log but hosts
> it under `.wiki/logs/operations.md` instead of `knowledge/`.)

## 7 · Isolation — engine ≠ data

**The engine and the data never mix on disk.**

The program lives in a hidden `.wiki/` folder; the operator's knowledge lives in the
vault. Updating the tool never touches the data; the data never carries engine state.
(Corollary: a config change isn't done until its migration writes the new key into
operator vaults in the same commit.)

> "The vault holds data. The `.wiki/` directory holds the engine. They never mix on
> disk." — **ours** (`README.md`, `AGENTS.md`)

## 8 · Lifecycle — forget by recency, not by score

**Old, untouched, unreferenced pages go cold by recency-tiering — never by a numeric importance score.**

Karpathy's wiki accumulates without forgetting; **this is our addition.** If a page
hasn't been touched in months and no new source references it, it *is* cold — that
mtime signal moves it to the background (active vs. archive), and the dream-cycle can
re-activate it on demand. We deliberately do **not** build numeric decay/recall-scoring
("the lever you build when you haven't taken lifecycle-tiering seriously").

> "if an article hasn't been touched in 6 months and no new source references it, it is
> cold — that's the signal, not a derived score." "Order matters." — **ours**
> (`.ytstack/backlog/architecture-scaling-2028.md`)
>
> Karpathy's gist: **no verbatim on forgetting** — the concept is absent there.

## 9 · Integrity — substrate is subject, not instruction

**The agent treats inputs as material to read, never as commands to obey.**

Substrate routinely contains literal change-instructions captured from past sessions
("rename X", "delete Y"). The compile agent must read them as *subject matter*, never
execute them — its write authority is hard-scoped to `knowledge/`, enforced in code, not
just asked for in the prompt.

> "substrate routinely contains literal change-descriptions captured from prior
> engine-development sessions. The agent reads them as instructions and acts on them
> with whatever filesystem authority you gave it." — **ours** (`AGENTS.md` HARD rule)

## 10 · Scope — map, don't act

**The wiki describes what is; it does not act for you.**

It maps the operator — it does not run to-dos, send messages, hold mutable task-state,
or change external tools. Anything that *acts* on the map (task sync, automation) is a
separate, operator-gated consumer downstream of the compiler — never the compiler itself.

> "Karpathy's and Cole Medin's concepts both scope themselves to reference content only;
> tasks are out." — **ours** (`docs/concept.md`)

---

## Runner-ups

Strong invariants that didn't make the core ten — promote one if a core rule ever
proves redundant:

- **Provider discipline** — one provider per role (compile = Claude SDK, local passes =
  Ollama), no silent fallback either direction; no LLM for deterministic work (scoring,
  aggregation, table-lookup stay pure-Python); meter tokens per `(provider, model)`,
  never dollars.
- **Distill, don't cite (provenance)** — provenance lives in `compiled_from:` frontmatter
  and the article's Sources section to *durable* substrate; the body distills, it does not
  body-link ephemeral/pruned mirrors. (Has a documented nuance — citability is a
  per-substrate lifecycle property, not a surface-shape one.)
- **Propose, don't auto-mutate (operator gate)** — autonomous or destructive operations
  are operator-gated, dry-run by default, and propose-only for ambiguous cases (e.g.
  concept↔concept contradictions).

## On "compile, don't retrieve" and the Karpathy lineage

The `raw/` → `knowledge/` shape and the compile-don't-retrieve choice are Karpathy's;
the session-capture pattern is Cole Medin's. Rules 1, 7, 8, 9, 10 are this project's
own extensions on top — most notably **forgetting** (rule 8, absent from Karpathy) and
**map-not-act** (rule 10, the deliberate boundary this project draws around itself). M005
(tasks surfaced inside entity pages) is the one conscious deviation from rule 10's "tasks
are out" — surfacing commitments (descriptive) is in scope; managing them (operational)
is not.

Full design rationale: [`docs/concept.md`](concept.md). Architectural decisions:
[`.ytstack/DECISIONS.md`](../.ytstack/DECISIONS.md). Scaling/forgetting roadmap:
[`.ytstack/backlog/architecture-scaling-2028.md`](../.ytstack/backlog/architecture-scaling-2028.md).
