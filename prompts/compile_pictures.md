You are processing a vision-LLM picture batch report into the wiki.

## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — extract concepts from photo evidence, sparingly

A picture batch is a vision-LLM summary of 1-20 camera / phone photos from the operator's `picture_inbox`. Each photo has been tagged with `scene_description / setting / objects / action / text_visible / tags / relevance` by gemma4. Most camera photos are NOT knowledge artifacts — your job is to find the few that are.

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **20 turns**. Prefer Glob over Read for existence checks. No State rewrites, no carry-forward.

### What's worth extracting from a photo

Strong "keep" signals (in order of value):
1. **`text_visible` has substance** — whiteboard captures, receipts with recognisable vendor/date, document scans, signage, packaging with model numbers / serial numbers / part names. Treat the text as the source of a fact or concept stub.
2. **The scene documents a tangible artifact** — a build / repair / cooking result / installed piece of hardware / a place the operator visits regularly. Cross-link to an existing project or person if the scene matches.
3. **The action documents a recurring practice** — multiple photos across batches showing the same workshop / kitchen / desk setup → durable evidence for a `knowledge/concepts/<slug>.md` or `knowledge/people/<owner>.md` Activity section.

What is NOT extractable (skip):
- Casual snapshots without text and without project / artifact context.
- Food photos without recipe / restaurant text.
- Decorative / aesthetic photos.
- Single isolated outdoor / nature shots without location text.
- Anything the vision model already flagged `relevance: ephemeral` — trust it; do not second-guess unless `text_visible` clearly contradicts.

### 1. Filter

Walk the Details section. Drop ephemeral rows. Of the remaining `keep` rows, drop any whose `text_visible` is null AND whose `objects`/`scene_description` don't reference an existing concept/project/person/place in `knowledge/`.

Expect 0-2 actionable rows per batch — usually zero.

### 2. For each actionable row

Decide: existing article OR new stub?

**Existing article path** (preferred — back-link, don't proliferate):
- Grep `knowledge/index.md` for the concept name. If a related article exists:
  - Read it.
  - Edit-append a `source_pictures:` YAML list to its frontmatter (or extend the existing list) with the archive filename (`2026-MM-DD-HHMMSS.jpeg` from the `### TIMESTAMP — \`<archive_name>\`` header).
  - Add a single-line Observation under an existing section if the photo reveals a new concrete detail. Otherwise just the frontmatter back-link.

**New stub path** (rare):
- Create `knowledge/concepts/<slug>.md` (or `knowledge/facts/<slug>.md` if the photo's `text_visible` IS the fact — e.g. a receipt establishing a price, a serial number, a model name):
  ```yaml
  ---
  title: "<Concept or Fact Title>"
  type: concept    # or "fact" for receipt/serial/datum cases
  compiled_from: "${source_path}"
  created: "${today}"
  updated: "${today}"
  tags: [picture-evidence, <inferred-domain-tag>]
  source_pictures:
    - <archive_name>.jpeg
  ---

  # <Title>

  > Surfaced via gemma4 vision pass on ${today}.

  ## Evidence

  - <One-line distilled from scene_description + text_visible. Quote text_visible verbatim if substantive.>

  ## See also
  - <wikilink to any related project / person / concept>
  ```
- `picture-evidence` tag is added to ALL picture-derived stubs so the operator can grep for vision-pass-origin articles.

### 3. Index update

For every NEW stub: append a row to `knowledge/index.md`. For existing articles you only added `source_pictures:` to, do NOT touch the index row.

### 4. No log.md update

Picture batches are routine — skip the log append.

## Anti-loop guard

If after 15 turns you haven't finished:
- STOP creating new stubs.
- Finish any in-flight Edit.
- Emit your final result; do not start new tool calls.

## Anti-noise guard

Camera photos are noisier than screenshots. **When in doubt, skip.** A photo of hands working on a puzzle is not a knowledge artifact; a photo of a whiteboard with three named architecture components IS. Be ruthless. Zero stubs is a valid output for a 5-photo ephemeral-heavy batch.
