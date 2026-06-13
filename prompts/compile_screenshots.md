You are processing a vision-LLM screenshot batch report into the wiki.

## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — extract concepts + back-link source screenshots

A screenshot batch is a vision-LLM summary of 30-100 desktop captures from a single operator-session. Each screenshot has been tagged with App / Project / Summary / Tags by gemma4. Your job is **lean and additive**:

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **30 turns**. Prefer Glob over Read for existence checks; one Write per substantive concept beats three Reads of "maybe related" articles. No State rewrites, no carry-forward, no resolution-detection — that's transcript-substrate work, not screenshot-substrate work.

### 1. Identify 3-7 substantive concepts in the batch

Scan the Details section for recurring themes across multiple screenshots. **Examples of substantive:** a recurring app/tool the operator hadn't documented yet, a debugging pattern visible in multiple frames, a project-specific workflow visible in IDE/terminal frames. **Examples of non-substantive (SKIP):** a single screenshot of a website the operator visited once, generic UI states without project signal, ephemeral context (search bars, login pages).

Quality bar: a concept is substantive only if at least 2 screenshots in the batch contribute to it OR the single screenshot is clearly project-defining (e.g. a never-before-seen architecture diagram). When in doubt, skip.

### 2. For each substantive concept

Decide: existing article OR new stub?

**Existing article path:**
- Grep `knowledge/index.md` for the concept name. If a related concept article exists in `knowledge/concepts/<slug>.md`:
  - Read it.
  - Edit-append a `source_screenshots:` YAML list to its frontmatter (or extend the existing list) with the original PNG filenames from this batch that informed the article. The PNG filenames are in the `### TIMESTAMP — \`Screenshot YYYY-MM-DD at HH.MM.SS.png\`` headers — copy them verbatim.
  - Optionally update the `updated:` date to today.
  - Do NOT modify the body unless the new screenshots reveal something concrete the existing prose missed.

**New stub path:**
- Create `knowledge/concepts/<slug>.md` with the standard concept frontmatter shape:
  ```yaml
  ---
  title: "<Concept Title>"
  type: concept
  compiled_from: "${source_path}"
  created: "${today}"
  updated: "${today}"
  tags: [screenshot-evidence, <inferred-domain-tag>]
  source_screenshots:
    - Screenshot YYYY-MM-DD at HH.MM.SS.png
    - Screenshot YYYY-MM-DD at HH.MM.SS.png
  ---

  # <Concept Title>

  > Surfaced via gemma4 vision pass on ${today}. Concrete evidence: <one-line summary distilled from the screenshot summaries>.

  ## Observations

  - <Bullet per substantive screenshot, citing the timestamp + app + what it showed>.

  ## See also
  - <wikilink to any related project/concept page surfaced in the batch>
  ```
- Domain tag inference per compile_main.md rules (operator's stack list). The `screenshot-evidence` tag is added to ALL screenshot-derived stubs so the operator can grep for vision-pass-origin articles.

### 3. Index update

For every NEW stub you created in step 2, append a row to `knowledge/index.md`. For existing articles you only added `source_screenshots:` to, do NOT touch the index row — the back-link doesn't bump the `updated:` semantic.

### 4. No operations log update

Screenshot batches run frequently — logging each one bloats `.wiki/logs/operations.md`. Skip the log append step.

## Anti-loop guard

If after 25 turns you haven't finished:
- STOP creating new stubs (remaining substantive concepts can wait for the next batch).
- Finish any in-flight Edit.
- Emit your final result; do not start new tool calls.

Screenshot extraction is back-linking, not deep synthesis. The right output is small: 0-3 new stubs + N existing-article source_screenshots appends per batch.

## Anti-noise guard

Be ruthless about substantiveness. Bad pattern: creating a stub for every distinct app that appeared in any screenshot. Good pattern: only create/update articles when the screenshots reveal something durable about the operator's work. A passing glance at a website is not a knowledge artifact.

${output_language_instruction}
