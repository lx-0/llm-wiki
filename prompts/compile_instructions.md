${owner_block}

# Compile a project's agent-instructions document

You are reading a project's `AGENTS.md` / `CLAUDE.md` / `README.md` that was
accidentally ingested as a Claude-Code memory. It is NOT a memory — it is
the agent-instruction document for a specific project repo.

Your job: extract the **project identity** + **2-4 substantive conventions
or gotchas** into a single Timeline-append on the matching project page.
NO cross-link fanout. NO concept-stub creation. NO multi-page Edits.

## Source

**File:** `${source_path}`
**Today:** ${today}

```
${source_content}
```

## What to extract

1. **Project identity.** The slugified project name. Usually visible in:
   - `origin:` frontmatter path (e.g. `.../projects/foo-bar/AGENTS.md` → slug `foo-bar`)
   - First H1 of the body ("# foo-bar" or "# AGENTS.md (foo-bar)")
   - `project:` or `tags:` frontmatter field
2. **2-4 conventions or gotchas.** Pick the most load-bearing ones — the
   things a contributor MUST know. Skip generic boilerplate.

## Where to write

Glob for `knowledge/projects/<slug>.md`.

If it exists: Edit-append ONE Timeline entry under `## Timeline` (newest-first):

```
- **${today}** — Agent-instructions doc sync: <one-line summary>. ([[<source_path without .md>]])
```

If it does NOT exist: do NOT create a new project page. Append to
`knowledge/index.md` so the source stays discoverable.

## Hard rules

- Make **at most 2 Edit calls** total.
- Do NOT Read other knowledge/ articles. Do NOT Glob beyond the single
  project-page lookup above.
- Do NOT create concept stubs, takes, or connection-articles.

## Hard facts (always-true context)

${facts_md}
