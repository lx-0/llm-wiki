---
name: llm-wiki
slug: llm-wiki
created: 2026-05-02T09:08:51Z
updated: 2026-05-02T09:08:51Z
---

# llm-wiki

**One-liner:** A self-cartography engine for solo knowledge workers — ingests daily logs, AI-agent memories, clippings, and other source streams into an always-current LLM-compiled wiki that the operator and their AI agents read from daily, with a depersonalized scale-out path to team and company knowledge.

## What this project is

An opinionated LLM-driven knowledge-compilation engine. Two-tier architecture: the engine code, configuration, and engine documentation live under `<vault>/.wiki/`; the user's actual Obsidian-style knowledge base (the "vault") owns the data — `raw/`, `daily/`, `knowledge/`, `inbox/`, `reports/`. The pipeline ingests raw materials and synthesizes structured articles via LLM compilation, rendered for Obsidian.

Surface framing: "personal-knowledge OS." Deeper framing: **self-cartography you actually use** — externalize parts of one's thinking that currently live in scattered substrates (daily logs, agent memories, clippings, other streams) into a navigable, machine-readable, AI-consumable map *that is read daily* by both the operator and their AI agents. The wiki is not an archive to be left behind; it is a working surface that gets refined by being used.

## Why it exists

A solo knowledge worker's thinking lives in too many partial substrates: daily notes capture behavior, AI-agent memories capture working thought, clippings capture curiosity, ad-hoc files and exports capture everything else. Each is queryable in isolation but not as a whole, and most are illegible even to the person who produced them. Cross-project memory loss, memory bloat in agent stores, daily-log archeology, and knowledge transfer to future-self all surface as concrete pain points (see `OFFICE-HOURS-self-cartography-engine.md` use moments).

Existing tools either solve a slice (claude-memory = agent memory only; Obsidian = manual note-taking) or solve a different problem (Notion = team docs; RAG systems = retrieval, not compilation). llm-wiki is the compilation layer that sits *between* raw substrates and active consumption — by humans reading and by agents prompting — opinionated about the pipeline shape because solo + AI-driven implies different ergonomics than team + human-only.

## Success criteria

Concrete signals, in rough order of when each becomes meaningful:

1. **Engine reproducibility:** any user can clone the repo, run `install.sh <vault>`, and have a working compilation pipeline against their own vault within 10 minutes. Tested 2026-04 onwards.
2. **Compile-cycle stability:** weekly compile runs across all configured collectors complete without manual intervention; failures are observable and fixable from logs.
3. **Read-share-edit ratio shifts:** the operator reads compiled wiki articles more often than they edit raw substrates. Measured informally; signal that the compilation produces value, not just structure.
4. **AI-agent reuse:** when working in any project, agents reach for `knowledge/` articles before scanning raw memories. Cross-project memory loss (use moment #1) measurably reduced.
5. **Multi-vault ingest** (post-M001): the engine can index more than one vault at a time, eliminating the blind-spot of vaults that fall outside the active install.
6. **Depersonalized scale-out** (long-horizon): same compilation pattern produces a team or company wiki from depersonalized inputs, without architectural rewrites.

## Current status

Initialized 2026-05-02 from `OFFICE-HOURS-self-cartography-engine.md` pitch. No milestone planned yet — `ytstack:plan-milestone` will define M001 ("Engine Bootstrap Polish"). Existing artifacts (`docs/design-decisions.md`, `docs/concept.md`, `docs/PROCESS.md`, `docs/plans/`, claude-memory `project_*.md`) need a manual brownfield-detect-analyze-migrate pass into `.ytstack/` shape — tracked as the upstream ytstack M010 (PR #15).
