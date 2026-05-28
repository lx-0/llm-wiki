You are extracting durable knowledge from an arbitrary substrate file.

${owner_block}
## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — lean concept extraction + cross-linking

This is the **default lean prompt** for any substrate type that doesn't have a dedicated handler in `SUBSTRATE_PROMPTS` (compile.py). Designed to be safe: cheap to run, never loops, produces durable value when there is value to produce, exits quietly when there isn't.

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **12 turns**.

**Critical:** This is NOT the dialog-substrate prompt. Do NOT do State+Timeline carry-forward, Action Item routing, resolution-detection, or stale-flagging — those operations belong to `compile_main.md` and only apply when the source carries first-person commitments or attributed dialog (jamie/gmeet/voice transcripts). Routing arbitrary substrate through that heavy shape is what cost the operator $2-5/file on max_turns-loops earlier in this engine's history.

### 1. Decide: is there extractable knowledge?

Skim the source. Many substrate types are metadata, telemetry, or one-off captures with no durable concept inside. If the source is:

- Pure metadata (folder listings, message counts, log timestamps)
- A copy of something already in `knowledge/` (rerun, sync, replay)
- A single ephemeral observation with no recurring pattern

→ Emit a brief "no extractable concept" result and exit. No Writes, no Edits, no index touch.

### 2. If there IS extractable knowledge

Identify **at most 3 durable concepts** the source surfaces. "Durable" means: would still be useful in 6 months, distinct from existing wiki content, specific enough to anchor future search. Vague abstractions ("software engineering", "AI patterns") are not durable; specific patterns ("Drizzle journal file requires manual entry for hand-written migrations") are.

For each concept:

1. **Grep `knowledge/index.md`** for the concept name + 1-2 related keywords.
2. **Existing article hit?** Read it; decide if the source adds new information.
   - Yes → Edit-append a paragraph under an appropriate `##` heading, cite `${source_path}` in a footnote-style line: `_(${today} · `${source_path}`)_`. Update the `updated:` frontmatter date. Do NOT touch State blocks if the article is `type: person|project` — that's the dialog-substrate's job.
   - No → no action; the existing article already covers it.
3. **No existing article + concept is genuinely new?** Create a minimal stub at `knowledge/concepts/<slug>.md`:
   ```markdown
   ---
   title: "<Concept Title>"
   type: concept
   compiled_from: "${source_path}"
   created: "${today}"
   updated: "${today}"
   tags: [<inferred-domain-tag>]
   ---

   # <Concept Title>

   > Surfaced from `${source_path}` on ${today}.

   <2-4 sentence distillation of what the source revealed about this concept>.

   ## See also
   - <wikilink to any related existing article you encountered>
   ```
   Domain tag inference per AGENTS.md rules (operator stack list).

### 3. Index update (only for new stubs)

For each new stub you created, append one row to `knowledge/index.md`. Existing articles you only appended a paragraph to: do NOT touch the index row (the paragraph isn't significant enough to bump the index summary).

### 4. No operations log update

The default prompt runs on many substrate types per batch. Logging each one bloats `.wiki/logs/operations.md`.

## Anti-loop guard

If after 9 turns you haven't finished:
- STOP creating stubs.
- Finish any in-flight Edit.
- Emit your final result; do not start new tool calls.

The right output for the default prompt is small: 0-2 article touches per file. Anything more, the substrate likely deserves a dedicated entry in `SUBSTRATE_PROMPTS` — flag that in the result so the operator can spot the pattern.

## Anti-noise guard

When in doubt, do nothing. Better to miss a fuzzy concept than create a noise stub that pollutes the wiki forever. The operator can re-prompt or write the article manually if needed.
