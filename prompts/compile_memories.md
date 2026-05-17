You append one Timeline line to a project page. Mechanical, 2-3 turns.

## Hard facts (override anything in the source material)

${facts_md}

## Pre-resolved inputs

The engine has already resolved the target page for you. Trust these values.

- **Source file:** `${source_path}` (this is the memory excerpt — a memory-sync single file OR one chunk of a memory-seed aggregate)
- **Project slug:** `${project_slug}`
- **Target project page:** `${project_page}`
- **Date:** `${today}`

A `## Timeline` section is guaranteed to exist on the target page (engine bootstrapped it if missing).

## Source material

```
${source_content}
```

## Your task — 2 turns

### Turn 1 — Read

Read `${project_page}` once. You need to see the file to make a valid Edit.

### Turn 2 — Edit-append one Timeline line

Edit `${project_page}`. Insert ONE new line directly under the existing `## Timeline` heading (newest-first ordering — your line goes ABOVE any existing entries that follow the heading):

```
- **${today}** | `${source_path}` — Memory sync: <one-line summary of the most distinctive pattern or fact in the excerpt>.
```

Replace `<one-line summary…>` with a single-sentence distillation drawn from the excerpt. Lean factual, not interpretive. ≤120 chars including the date prefix.

Then emit `{"status": "ok", "project": "${project_slug}"}` and STOP.

## Hard prohibitions

- ❌ No Glob, Grep, or Bash. The engine pre-resolved the page; do not search.
- ❌ No edits to ANY file other than `${project_page}`.
- ❌ No new sections, no concept stubs, no `knowledge/index.md` edits, no log.md edits.
- ❌ No State-block edits on the project page. Memories are not commitments — Timeline append only.
- ❌ No multi-line Timeline entries. One line per memory excerpt.

## Failure branch

If Read returns content that does not contain `## Timeline` (engine bootstrap should have prevented this — flag it as a real bug), emit `{"status": "timeline_missing", "page": "${project_page}"}` and STOP. Do not attempt to create the section yourself.
