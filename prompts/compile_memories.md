You are extracting cross-project knowledge from an operator-memory file.

## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — cross-link memory content into existing knowledge

This is an operator-memory file synced from a project workspace:

- **`type: memory-sync`** — a copy of a project's `AGENTS.md` / `CLAUDE.md` / per-file Claude memory. The frontmatter identifies the source project; the body is the verbatim memory content.
- **`type: memory-seed`** — an aggregated dump of multiple per-file memories for a project. Each memory entry is a `##` section with a `Why:` and `How to apply:` line.

Your job is **lean cross-linking**, not synthesis: identify the project + 1-3 substantive patterns, append Timeline entries to existing knowledge pages, optionally create a single concept stub if a recurring pattern across multiple memories deserves its own page. You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **15 turns**.

### 1. Identify the project context

The frontmatter has `project:` (memory-sync) or the filename slug (memory-seed). Slugify and search `knowledge/projects/`:

- Glob `knowledge/projects/<slug>.md` — exists?
- If yes → that's the entity to back-link to.
- If no → check `## See also` / wikilinks in the memory body for an alternative project mention. Slugify those + Glob.
- If still no match → SKIP entity routing entirely (don't create a project stub from memory alone — wait for substrate that introduces the project as the subject, not as a reference).

### 2. Append a Timeline entry to the matched project page

If you matched a project page in step 1, Edit-append one Timeline line under its `## Timeline` heading (newest-first):

`- **${today}** | \`${source_path}\` — Memory sync: <one-line summary of the most distinctive pattern in this file>.`

Do NOT touch the project's State block. Do NOT extract Action Items (operator memories aren't commitments). Append-only.

### 3. Substantive recurring-pattern stub (optional, max 1 per file)

For memory-seed files specifically (which aggregate many memory entries), if you spot a recurring pattern across **multiple** entries that isn't already in `knowledge/concepts/`, create ONE concept stub:

```markdown
---
title: "<Pattern Name>"
type: concept
compiled_from: "${source_path}"
created: "${today}"
updated: "${today}"
tags: [operator-pattern, <inferred-domain-tag>]
---

# <Pattern Name>

> Distilled from operator's project memories (${source_path}) on ${today}. The pattern recurs across N+ memory entries in this project.

## Description

<2-3 sentence distillation of the pattern>.

## Why operator captured it

<one-line from the memory's "Why:" field, distilled across the entries>.

## See also
- [[knowledge/projects/<matched-project>]]
```

The `operator-pattern` tag lets the operator grep for memory-derived articles vs substrate-derived ones.

**Anti-noise**: skip stub creation if you're not certain the pattern is durable. Most memories are project-specific feedback that doesn't deserve its own concept page; just the Timeline append is enough.

### 4. Index update (only for new stubs)

If you created a stub in step 3, append a row to `knowledge/index.md`. Timeline-only updates to existing project pages: no index touch.

### 5. No log.md update

Memory syncs run frequently (per session-end). Skip the log append step.

## Anti-loop guard

If after 12 turns you haven't finished:
- Skip stub creation (the next memory-sync of the same project will resurface the pattern).
- Finish any in-flight Edit.
- Emit your final result; do not start new tool calls.

Memory-sync extraction is back-linking, not deep synthesis. The right output is small: 1 Timeline append + maybe 1 stub per file.
