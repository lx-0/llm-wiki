# Naming

This project implements [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

**"LLM Wiki"** is the de-facto community term for the pattern. Karpathy used both "LLM Knowledge Bases" (Tweet, 2026-04-03) and `llm-wiki` (his own gist filename). Of the top 10 GitHub implementations within four weeks of his post, nine use "LLM Wiki" in repo name or description. We follow that convention.

## Contents

- [Three naming layers](#three-naming-layers) — pattern · code · user-branding
- [What we explicitly do **not** call this](#what-we-explicitly-do-not-call-this) — and why
- [When you mean "the wiki"](#when-you-mean-the-wiki) — disambiguating output vs tooling vs system

## Three naming layers

| Layer | Term | Rationale |
|---|---|---|
| Pattern descriptor | "LLM Wiki" | Karpathy + community standard |
| Code, paths, vars | `wiki`, `.wiki/`, `WIKI_DIR`, `WikiConfig` | Internal consistency |
| User branding | (free choice) | The tooling does not impose a name on the user's vault |

## What we explicitly do **not** call this

- "Brain" / "Exobrain" / "Second Brain" — these refer to Tiago Forte's broader PKM concept and are semantically broader than what we do.
- "Knowledge Compiler" / "Memory Compiler" — describes the engine, not the artefact (the wiki).
- "Knowledge Base" — too generic, collides with RAG/vector-DB usage.

## When you mean "the wiki"

Be specific: most of the time you mean either

- **the compiled output** — articles in `knowledge/` (Karpathy: "the wiki")
- **the tooling layer** — code in `.wiki/` (this repo)
- **the system as a whole** — say "LLM Wiki implementation"

The overlap is real and common; pick the precise sense in writing.
