You are cross-referencing a daily digest into existing knowledge entities.

${owner_block}
## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — cross-link, don't synthesize

A daily digest (`daily/<date>.md`) is ALREADY a distillation. The per-source substrates that fed it (`daily/<date>/sessions.md`, `meetings.md`, `voice.md`, `health.md`, `email.md`) have already been compiled or will be compiled separately — that's where commitments, decisions, and Action Items get extracted under the two-layer carry-forward shape. This pass does NOT re-do that work.

What this pass DOES: append "mentioned in today's digest" Timeline entries to **existing** entity pages, ensure project/concept pages cited by the digest exist as stubs, and update the index for any new stubs. Append-only, no State rewrites.

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **12 turns**. If you find yourself nearing the cap, stop — emit your final result rather than continuing to loop.

### 1. Identify entities mentioned

Scan the digest for:
- **People** named explicitly (first names, full names, @mentions)
- **Projects** named (typically the operator's product list — `fleet`, `openclaw`, `paperclip`, `llm-wiki`, etc.)
- **Concepts** referenced via existing `[[knowledge/concepts/<slug>]]` wikilinks

You do NOT scan substrate captures referenced from the digest (e.g. `daily/2026-05-15/sessions.md`) — only the digest body itself.

### 2. Append Timeline entries to EXISTING entity pages

For each identified entity:

1. **Slugify** the name per AGENTS.md rules.
2. **Glob** `knowledge/{people,projects}/<slug>.md`. If it does NOT exist: **SKIP this entity** (do not stub from digest mentions — wait for proper substrate introduction).
3. If it EXISTS: append ONE Timeline line via Edit, newest-first under the `## Timeline` heading:
   `- **${today}** | \`${source_path}\` — Mentioned in daily digest: <one-line context from digest>.`

   Do NOT touch the State block above `---`. Do NOT add Action Items or Open Threads. Do NOT carry-forward, demote, or stale-flag — that's the dialog-substrate pass's job. Append-only, one entry per entity per source.

### 3. Concept stubs for new wikilinks

If the digest contains `[[knowledge/concepts/<slug>]]` wikilinks pointing to non-existing files, create minimal stubs at `knowledge/concepts/<slug>.md`:

```markdown
---
title: "<Slug-Derived Title>"
type: concept
compiled_from: "${source_path}"
created: "${today}"
updated: "${today}"
tags: [digest-mention, <inferred-domain-tag>]
---

# <Title>

> First referenced via daily digest on ${today} (`${source_path}`).

(Operator can flesh this out when the concept proves recurring.)
```

Domain-tag inference per compile_main.md rules (look at the digest's other tags / context). Default to `yesterday` if unclear.

### 4. Index update (only for newly created stubs)

For each newly created concept stub, append a row to `knowledge/index.md`:
`| [[knowledge/concepts/<slug>]] | <one-line summary> | ${source_path} | ${today} |`

Existing entity rows do NOT need touching (Timeline appends don't bump `updated:` on the row — that's reserved for State changes).

### 5. No operations log update

Daily compiles run for every day's digest. Logging each one bloats `.wiki/logs/operations.md`. Skip the log append step.

## Anti-loop guard

If after 9 turns you haven't finished:
- STOP creating stubs (remaining new concepts can wait for the next pass).
- Finish any in-flight Timeline edit.
- Emit your final result; do not start new tool calls.

This is cross-linking, not synthesis. The right output is small.

${output_language_instruction}
