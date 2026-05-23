# AGENTS.md — Personal Knowledge Base Schema

> Adapted from [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [Cole Medin's claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler).
>
> This file is a **template**. After install, edit it to match your vault — especially the "Vault Owner" and "Language" sections. The compiler reads this on every run, so anything you put here becomes the contract.

## The Compiler Analogy

```
raw/ + daily/   = source code    (your inputs — the raw material)
LLM             = compiler       (extracts and organizes knowledge)
knowledge/      = executable     (structured, queryable knowledge base)
lint            = test suite     (health checks for consistency)
queries         = runtime        (using the knowledge)
```

You don't manually organize your knowledge. You have conversations and curate sources, and the LLM handles the synthesis, cross-referencing, and maintenance.

## Vault Owner

> **EDIT THIS SECTION.** Replace with your own context — role, current projects, products, the people and entities you collaborate with. The compiler uses this to disambiguate references and maintain `knowledge/people/` + `knowledge/projects/` consistency.

**Wiring (do this first, before the prose below):**

1. Set `personal.implicit_operator_author: <your-slug>` in `.wiki/config.yaml` (e.g. `alex`). The slug becomes the filename of your person page.
2. Make sure `knowledge/people/<your-slug>.md` exists (`type: person`, with `aliases:`). The compile agent reads this on demand to resolve "I" / "we" / "my company" in source material and to attribute first-person beliefs from sources that have no explicit `author:` frontmatter.

With those two in place, the engine auto-injects a short "## Operator / vault owner" block at the top of every substrate compile prompt — no manual maintenance needed. Leave `implicit_operator_author` as `null` for multi-tenant vaults; the block is then omitted and unattributed content stays generic.

The freeform prose below is **additional** context (role, current projects, collaborators). It does not replace the wiring above — it complements it.

Example shape (delete and rewrite):

```
Operator: <Name>, <role/title>.
Active projects: <project A>, <project B>.
Frequent collaborators: <person 1> (<role>), <person 2> (<role>).
External tools / services frequently referenced: <tool X>, <service Y>.
```

## Language

> **EDIT THIS SECTION** to match your working language preferences.

- Schema, code, git: English.
- Wiki articles: match the language of the source (default: English; switch per-source).
- Conversations: <your preference>.

---

## Architecture

### Layer 1: `raw/` — Curated Sources (Immutable)

Manually curated source documents. The LLM reads from them but **NEVER modifies them**. This is the ground truth. Once a file is in `raw/`, it stays forever.

```
raw/
├── articles/        # PERMANENT: web articles, blog posts, HTML originals + enriched markdown
├── papers/          # PERMANENT: PDFs, research papers (text-extracted)
├── notes/           # PERMANENT: collector output (one subfolder per collector)
│   ├── email/       # Collector: email metadata + deltas + deep scans
│   ├── calendar/    # Collector: calendar metadata
│   ├── browser/     # Collector: browser bookmarks/history/tabs
│   ├── tabs/        # Collector: Firefox Simple Tab Groups snapshots
│   ├── screenshots/ # Collector: screenshot Vision-LLM descriptions
│   ├── pictures/    # Collector: camera/phone-photo Vision-LLM batches (folder-watch on personal.picture_inbox)
│   ├── youtube/     # Collector: video metadata + transcript + comments (per-video markdown)
│   └── health/      # Collector: daily biometric rollup (Oura) — `<year>/<date>--<account>.md`
├── transcripts/     # PERMANENT: meeting + audio transcripts
│   ├── jamie/       # Collector: Jamie AI meeting-notetaker (paired summary + diarised transcript)
│   └── gmeet/       # Collector: Gemini Meet Notes + Transcript Docs (Drive API; paired sections)
├── voice/           # PERMANENT: dictation transcripts (collectors/voice.py — folder-watch on personal.voice_inbox; punctuation pre-process via Ollama, raw text preserved in frontmatter `raw_transcript:`)
├── captures/        # PERMANENT: quick-capture notes (collectors/capture_collector.py — folder-watch on personal.capture_inbox; content-hash capture-ID in frontmatter, idempotent re-drop; file `capture-<id>.md`)
├── audio/           # PERMANENT: original audio files (referenced by transcripts)
├── memories/        # PERMANENT: seeded Claude Code memories
├── requests/        # MUTABLE: compiler-generated ingest requests (status changes)
└── suggestions/     # MUTABLE: compiler-generated optimization suggestions (status changes)
```

**Permanence rules:**

- All `raw/` subfolders are **permanent**. Files are never deleted, never modified. They are the immutable ground truth. The compiler reads them but never writes back.
- `raw/requests/` is the exception: request files have a `status` field that changes (pending → processing → done). The file itself is not deleted.
- `raw/suggestions/` is the second exception: suggestion files have a `status` field that changes (pending → approved/rejected → executed).
- `inbox/` lives **outside** `raw/` (at vault root) because it is **transient** — files are classified and moved into the right `raw/` subfolder by `process-inbox.py`. The inbox empties after processing.

Each source file has YAML frontmatter:

```yaml
---
type: article | paper | note | transcript
date: YYYY-MM-DD
origin: "URL or filepath or description"
tags: [topic1, topic2]
language: de | en
---
```

### Layer 2: `daily/` — Per-Day Operational Rollup

Two-shape since the 2026-05-15 `daily/`-as-rollup arc:

```
daily/
├── 2026-05-14.md              ← compile-stage digest (≤500 words, distilled)
└── 2026-05-14/                ← per-source append-only captures
    ├── sessions.md            ← Claude Code session-end hook captures
    ├── health.md              ← collectors/health.py — Oura daily one-liners
    ├── meetings.md            ← collectors/{gmeet,jamie}.py — meeting one-liners
    ├── voice.md               ← collectors/voice.py — dictation intakes
    ├── captures.md            ← collectors/capture_collector.py — quick-capture one-liners
    └── email.md               ← collectors/email_collector.py — delta links
```

**Subfolder (`daily/<date>/<source>.md`)** — append-only captures owned by exactly one writer each. All six writers go through `core.daily_capture` (fcntl-flocked, source-name validated against `KNOWN_SOURCES`). Failures in the rollup write never break the primary substrate write — they're side-effects on top.

**Root file (`daily/<date>.md`)** — the compile-stage digest. Written by the `daily-digest` agent (`prompts/agents/daily-digest.md`) or the `daily_digest_yesterday` piggyback (`scripts/daily_digest_runner.py`). Hard length cap (~500 words) so the digest stays a digest. Refuses to overwrite if the file already has non-digest frontmatter (operator-edit protection).

```markdown
---
title: "Daily — 2026-05-14"
type: daily-digest
date: 2026-05-14
sources: [sessions, health, meetings, voice]
---

# Daily — 2026-05-14

## Highlights
- 3-7 bullets across all substrates

## Physical
One-paragraph from Oura if health.md exists.

## Meetings / Voice notes / Email
Bullets / one-liners from each source's per-source capture.
```

Sessions captures inside `daily/<date>/sessions.md` follow the older per-session block format (header `### Session HH:MM`, key-exchanges, decisions, action-items) — hooks unchanged in shape, only relocated.

Migration of pre-2026-05-15 flat-daily files: `uv run python scripts/migrate_daily_to_rollup.py --vault <vault>`. Copies (not moves) `daily/<date>.md` → `daily/<date>/sessions.md`; idempotent re-runs are a no-op.

Lint `check_daily_consistency` flags: (a) subfolder-without-digest, (b) root-without-subfolder (legacy flat-daily), (c) unknown source names in the subfolder.

### Layer 3: `knowledge/` — Compiled Knowledge (LLM-Owned)

The LLM owns this directory entirely. Humans read it but rarely edit it directly.

```
knowledge/
├── index.md          # Master catalog — every article with one-line summary
├── log.md            # Append-only chronological build log
├── concepts/         # Atomic knowledge articles            (type: concept)
├── connections/      # Cross-cutting insights linking 2+    (type: connection)
├── qa/               # Filed query answers                  (type: qa)
├── people/           # Person pages (one per person)        (type: person)
├── projects/         # Project pages (one per project)      (type: project)
├── areas/            # Ongoing responsibilities (no end)    (type: area)
├── facts/            # Hard facts (human-owned, override sources)  (type: fact)
├── takes/            # Third-party beliefs (WHO believes WHAT)     (type: takes)
└── MOCs/             # Curated topic hubs (human-curated)   (type: moc)
```

Each article in `knowledge/` carries this YAML frontmatter:

```yaml
---
title: "Article Title"
type: concept | connection | qa | person | project | area | moc | fact | takes
compiled_from: "raw/articles/some-source.md"   # or list[] for multi-source
created: 2026-04-01
updated: 2026-05-02
tags: [topic1, topic2]
domain: company   # optional (M013) — one of CONFIG.personal.domains
                  # (default enum: company | personal | ai | meta).
                  # Cross-cutting life-domain axis, NOT a folder. Pure
                  # filter — never required; untagged articles appear in
                  # every view. `wiki query --domain <value>` filters
                  # answers to articles whose `domain:` matches. Lint
                  # `check_domain_value` warns on values outside the
                  # configured enum. Extend by adding to
                  # `personal.domains` in config.yaml. Spec:
                  # `.ytstack/backlog/domain-frontmatter.md`.
---
```

The `type:` field MUST match the destination folder. It is the single source of truth for substrate-type — Dataview queries, lint, dashboard charts, and the compile prompt all rely on it. Lint flags any article whose `type:` is missing or doesn't match its folder.

**Domain-tag rule (`concepts/` and `qa/` only):** the `tags:` list must include at least one *domain* tag — a name from your active stack/product list, not a generic type-word like `pattern` or `discipline`. The graph view colors nodes by domain tag; notes without one fall into a grey fallback bucket. Configure your domain list in `config.yaml` under `graph_view.domain_tags`; the engine default covers a known operator set (`fleet`, `openclaw`, `claude-code`, `yesterday`, `llm-wiki`, `paperclip`, `ytstack`, `township`, `pixeltales`, `lxw`). Lint check `check_concept_domain_tag` warns on non-conforming concepts; `check_qa_schema` also enforces `type: qa` presence + index-row presence on every `qa/` note.

`knowledge/facts/` is special: it is **human-owned via `wiki correct`**, never written by the compiler. Each fact carries `type: fact`, a `status:` (negation | disambiguation | clarification), an optional list of `negation_terms:` that lint greps across the rest of `knowledge/`, and an `applied:` flag that flips to an ISO timestamp once `wiki correct apply <slug>` has propagated the correction.

Every fact also carries a **`trust:`** tier and a **`sources:`** list (≥1, required at creation):

- `trust:` one of `confirmed` (externally verifiable artifact — URL, document, screenshot), `asserted` (user direct statement, no external artifact, default), `provisional` (hearsay, needs verification).
- `sources:` list of evidence pointers. Free-form: URL, vault-relative path, or sentinel like `user:<context>`, `screenshot:<file>`, `hearsay:<who>`.

Facts inject into compile and query prompts at the highest authority — they override any contradicting claim in raw sources. Within the facts block, they are sorted `confirmed` > `asserted` > `provisional` (then most-recently-updated first), and each is rendered with its trust tier and sources line so the LLM can weigh authority when two facts conflict.

Pre-trust legacy facts without `trust:` / `sources:` keys are rendered with reader-defaults (`asserted`, source `user:legacy-pre-trust-schema`) — no migration script is required, but `wiki correct edit <slug>` can backfill explicit values.

### Layer 4: This File (`AGENTS.md`)

The schema that tells the LLM how to compile and maintain the knowledge base. This is the "compiler specification." It co-evolves with the wiki.

---

## Analytical Surface — Operator Self-Reports (Air-Gapped from Compile)

Parallel to the Layer-1→4 ingest→compile→knowledge pipeline, the engine
ships a `reports/` surface for psychometric self-tracking. This is
**air-gapped** from the compile loop — analyst-agent output never
flows back into `knowledge/`, preventing a self-observation-bias
feedback. Reports use a different scope, different scoring layer,
different agents.

**CLI surfaces:**

```
wiki study list                                # show studies + status
wiki study run <study-id>                      # run all instruments + Pass-1 analyst
wiki study run <study-id> --instrument SLUG    # narrow to one
wiki study new <id> [--fork-from OTHER]        # create / clone
wiki study answer <study-id> <instrument> <item-id> <value>
                                               # operator answer for substrate-null items
wiki analyze                                   # Pass-1 all studies + Pass-2 cross-study
wiki analyze --study <id>                      # Pass-1 only on one study
wiki analyze --cross-study-only                # Pass-2 only (cross-study synthesis)
```

**Layout (vault-root sibling of `knowledge/`):**

```
reports/
  studies/<id>/
    manifest.yaml             # immutable spec (schedule, instruments)
    state.yaml                # engine-managed last_run_at + run_count
    operator_answers.yaml     # populated by `wiki study answer` — operator-supplied items
    runs/<UTC-ts>/
      instruments/<slug>.md   # per-instrument deterministic report with embedded methodology
      _summary.md             # cross-instrument meta-report (radar + sparkline + timelines)
      _analysis.md            # Pass-1 analyst — substrate-grounded prose
      charts/*.svg            # radar / coverage-sparkline / per-instrument-timeline
  analyses/<UTC-ts>.md        # Pass-2 cross-study synthesis output
```

**Key invariants:**

- Reports are **Informant Report**, not self-report — the LLM observer
  scores items from substrate. Use `wiki study answer` to provide
  explicit self-report for items marked `substrate_inferable: false`
  in their instrument's items.yaml (interior states the substrate
  can't reach).
- Air-gapped: `reports/` is excluded from compile.py's substrate
  scope via `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES`. Agents reading
  `daily/` / `raw/` / `knowledge/` MUST NOT also read `reports/` —
  feeds self-observation-bias.
- Every per-instrument report embeds its full methodology (items,
  cutoffs, prompt-version, model-id, scope-spec, evidence paths)
  inline. Reports are durable independent of the engine.

---

## Structural Files

### `knowledge/index.md` — Master Catalog

A table listing every knowledge article. The LLM reads this FIRST when answering any query, then selects relevant articles to read in full.

Format:

```markdown
# Knowledge Base Index

| Article | Summary | Compiled From | Updated |
|---------|---------|---------------|---------|
| [[concepts/some-concept]] | One-line summary | daily/2026-04-02.md | 2026-04-02 |
| [[connections/x-and-y]] | How concept X relates to concept Y | daily/2026-04-04.md | 2026-04-04 |
| [[people/alice]] | Collaborator on project foo | raw/notes/foo-spec.md | 2026-04-08 |
```

### `knowledge/log.md` — Build Log

Append-only chronological record of every operation.

```markdown
# Operations Log

## [2026-04-08T14:30:00+00:00] compile | Daily Log 2026-04-08
- Source: daily/2026-04-08.md
- Articles created: [[concepts/some-concept]], [[concepts/related-concept]]
- Articles updated: (none)

## [2026-04-08T15:00:00+00:00] query (filed) | "How do I handle X?"
- Consulted: [[concepts/some-concept]], [[concepts/middleware-pattern]]
- Filed to: [[qa/how-to-handle-x]]
```

---

## Article Formats

### Concept Articles (`knowledge/concepts/`)

One article per atomic piece of knowledge. Facts, patterns, decisions, preferences, and lessons.

```markdown
---
title: "Concept Name"
aliases: [alternate-name, abbreviation]
tags: [domain, topic]
sources:
  - "daily/2026-04-01.md"
  - "raw/articles/some-article.md"
created: 2026-04-01
updated: 2026-04-03
---

# Concept Name

[2-4 sentence core explanation]

## Key Points

- [Bullet points, each self-contained]

## Details

[Deeper explanation, encyclopedia-style paragraphs]

## Related Concepts

- [[concepts/related-concept]] - How it connects

## Sources

- [[daily/2026-04-01.md]] - Initial discovery
- [[raw/articles/some-article.md]] - Detailed reference
```

### Connection Articles (`knowledge/connections/`)

Cross-cutting synthesis that asserts a non-trivial CLAIM about how 2+ concepts relate. NOT a co-occurrence note, NOT a side-by-side restatement of either concept.

A connection article MUST:
1. **Name a load-bearing mechanism, contrast, dependency, or causal claim** between the linked concepts. If you cannot write 3 sentences of genuine synthesis that don't already appear in either linked concept, prefer an inline `[[wikilink]]` between the concepts over a standalone connection article.
2. **Cite each linked concept by `[[wikilink]]`** in the body. ≥2 distinct `knowledge/`-tree wikilinks (`daily/` and `raw/` references are sources, not endpoints).
3. **Declare the kind of relationship** in frontmatter with exactly one of:
   - `mechanism:` — "X enables Y because Z" / causal or mechanistic chain
   - `tension:` — "X contradicts / pulls against Y" / contrast or contradiction
   - `dependency:` — "Y cannot exist without X" / hard prereq with no further mechanism claim
4. **Body ≥ 50 words** below the frontmatter.
5. **Carry a domain tag** so the article anchors into the graph view's color groups (same rule as `type: concept`).

Lint enforces all five (see `scripts/lint.py:check_connection_depth` + `check_concept_domain_tag`). Rejected examples:
- `"X and Y both relate to AI"` → co-occurrence, REJECT.
- `"See also [[X]], [[Y]]"` → no claim, REJECT.
- 3-line body with just a `connects:` list → fails the word-count floor.

```markdown
---
title: "Connection: A2A Protocol enables Work Orchestration"
type: connection
mechanism: "A2A's task-state model provides the inter-agent dispatch primitive that the work-orchestration gap had identified as missing."
connects:
  - "concepts/a2a-fleet-communication"
  - "concepts/work-orchestration-gap"
sources:
  - "daily/2026-04-18.md"
tags: [fleet]
created: 2026-04-20
updated: 2026-04-20
---

# Connection: A2A Protocol enables Work Orchestration

## The Claim

The [[concepts/work-orchestration-gap]] surfaced on 2026-04-17 named "task dispatch between agents" as Fleet's missing primitive. One day later, [[concepts/a2a-fleet-communication]] adopted A2A, whose `a2a_tasks` table with 8 spec-defined states is exactly that dispatch primitive. The gap and the solution were discovered independently but the protocol's task model resolves the architectural hole the gap analysis predicted.

## Evidence

- `a2a_sendMessage` provides the dispatch verb the gap analysis required.
- 8 task states (`submitted`, `completed`, `failed`, ...) cover the review-and-retry cycle the gap had named as unhandled.
- See `daily/2026-04-18.md` for the architecture-decision context.
```

### Q&A Articles (`knowledge/qa/`)

Filed answers from queries. Every complex question answered by the system can be permanently stored.

```markdown
---
title: "Q: Original Question"
question: "The exact question asked"
consulted:
  - "concepts/article-1"
  - "concepts/article-2"
filed: 2026-04-05
---

# Q: Original Question

## Answer

[The synthesized answer with [[wikilinks]] to sources]

## Sources Consulted

- [[concepts/article-1]] - Relevant because...
- [[concepts/article-2]] - Provided context on...

## Follow-Up Questions

- What about edge case X?
```

### People Articles (`knowledge/people/`)

One page per person. Uses the **two-layer shape** (compiled-truth State block above `---`, append-only Timeline below). State is rewritten each compile pass; Timeline only appends.

```markdown
---
title: "Person Name"
type: person
aliases: []
tags: [person, role-or-context]
compiled_from:
  - "raw/transcripts/jamie/2026-04-15--review--abc.md"
  - "daily/2026-04-12.md"
created: 2026-04-01
updated: 2026-04-15
---

# Person Name

> One-paragraph executive summary: who, role, why they matter to the operator.

## State
- **Role:** VP Eng, Acme
- **Relationship:** former colleague

## Action Items
- [ ] Send the Q3 deck 📅 2026-05-20
- [ ] Follow up on Bob intro

## Open Threads
- Waiting on her intro to Bob (mentioned 2026-04-15)

## What they're building
[Free prose with [[wikilinks]] into concepts/projects.]

## See also
- [[knowledge/projects/yesterday-platform]] - Collaboration context
- [[knowledge/concepts/relevant-topic]] - Shared expertise

---

## Timeline
- **2026-04-15** | `raw/transcripts/jamie/2026-04-15--review--abc.md` — Reviewed Q1 roadmap; pushed back on inference-cost framing.
- **2026-04-12** | `daily/2026-04-12.md` — Mentioned during agent-config debugging session.
```

**Rules** (canonical in `prompts/compile_main.md` Instruction 3):

- **State block above `---`** is compiled truth — rewritten each compile pass from current substrate.
- **`## Action Items`** uses Obsidian-Tasks-plugin syntax exclusively: `- [ ]` (or `- [x]`) + optional `📅 YYYY-MM-DD`, `⏫` priority, `🔁` recurrence.
- **`## Open Threads`** lists waiting/blocked items as prose bullets, one per line. Distinct from Action Items: threads describe blocked state, action items are owned commitments.
- **`---` separator** between State and Timeline is mandatory.
- **`## Timeline`** below `---` is append-only and reverse-chronological (newest first). One entry per substrate touch: `- **YYYY-MM-DD** | \`raw/...md\` — short note.`

### Project Articles (`knowledge/projects/`)

One page per project. Same **two-layer shape** as People articles — State captures current project status; Timeline accretes substrate touches.

```markdown
---
title: "Project Name"
type: project
aliases: []
tags: [project, domain]
compiled_from:
  - "raw/notes/project-spec.md"
  - "daily/2026-04-01.md"
created: 2026-04-01
updated: 2026-04-08
---

# Project Name

> One-paragraph executive summary: what it is, why it exists, where it stands.

## State
- **Status:** active | paused | completed
- **Stack:** Next.js 15 + tRPC + Drizzle
- **Owner:** [[knowledge/people/jane-doe]]

## Action Items
- [ ] Ship S03 dashboard pane 📅 2026-05-22 ⏫
- [ ] Decide on auth-provider migration

## Open Threads
- Waiting on infra capacity decision (mentioned 2026-04-05)

## What it is
[Free prose with [[wikilinks]] into concepts/people.]

## Key Decisions
- [Decision with date and rationale]

## See also
- [[knowledge/people/jane-doe]] - Team member
- [[knowledge/concepts/relevant-pattern]] - Key pattern used

---

## Timeline
- **2026-04-08** | `daily/2026-04-08.md` — Architecture review with Jane; tRPC v11 confirmed.
- **2026-04-01** | `raw/notes/project-spec.md` — Initial spec doc.
```

Rules: same as People Articles (above) — see `prompts/compile_main.md` Instruction 3 for the canonical contract.

### Area Articles (`knowledge/areas/`)

One page per ongoing responsibility (CEO-Hat, llm-wiki Maintenance, Personal
Health Tracking, Apartment Logistics, ...). Areas differ from Projects in
that they have no finish line — they accrete Open Threads indefinitely and
retire only when the role itself ends.

```markdown
---
title: "Area Name"
type: area
status: active        # active | dormant | retired
tags: [domain]
created: 2026-05-16
updated: 2026-05-16
last_synthesized: 2026-05-16
---

# Area Name

> One-paragraph: what this responsibility covers, why it exists, who else
> (if anyone) shares it.

## Current State
- **Cadence:** ad-hoc / weekly / daily
- **Active surfaces:** dashboard, daily digest, ...
- **Health:** green | yellow | red

## Open Threads
- Long-running blocked / waiting items (areas accumulate these indefinitely;
  projects close them).

## Action Items
- [ ] Owned commitment 📅 2026-06-01

## Related
- [[knowledge/projects/some-project]]
- [[knowledge/people/some-collaborator]]

---

## Timeline
- **2026-05-16** | Area created.
```

**Rules:**

- **`status:` is mandatory** and must be one of `active | dormant | retired`
  (enforced by lint `check_area_status`). Distinct from project status — no
  `planning`, `in-progress`, or `done`.
- **No `deadline:` frontmatter** — areas have no finish line by definition.
- **Open Threads are first-class.** Areas are where long-running threads tied
  to a *role* live (e.g. "as CEO, I'm waiting on..."). Projects close threads;
  areas keep them.
- **Retired** ≈ archived; the page stays as historical record.
- **Picking project vs. area:** has a finish line → project; ongoing → area.
  If both apply, the area owns the long-term, the project owns the current
  push.

### Takes Articles (`knowledge/takes/`)

One file per **holder** (a named person OTHER than the operator). Append-only,
one-belief-per-line. Records WHO believes WHAT, with confidence + date +
source. The operator's own positions stay in `knowledge/facts/`; takes are
the parallel substrate for third-party attribution.

```markdown
---
title: "Takes — Jane Doe"
type: takes
holder: jane-doe
created: 2026-05-13
last_updated: 2026-05-13
---

# Takes — Jane Doe

- **2026-04-15** [high] · `raw/transcripts/jamie/2026-04-15--review--abc.md` — GPT-5 commoditizes agent platforms within 12 months.
- **2026-03-02** [medium] · `daily/2026-03-02.md` — Inference cost halves every 9 months, not 6.
```

**Rules:**

- One file per holder, filename = slugified holder name.
- Append-only, one take per line. Canonical shape (lint enforces):
  `- **YYYY-MM-DD** [low|medium|high] · \`source-path\` — belief.`
- Confidence rubric: `high` = stated multiple times consistently;
  `medium` = stated once, explicit; `low` = offhand or hedged.
- Writers: `wiki take add/remove` for operator-typed entries; the
  post-compile extract-takes producer (gated by `features.extract_takes`).
- Compile-side consumption: when distilling a `type: person` page,
  compile reads `knowledge/takes/<slug>.md` and cites takes by date in
  the State block. Facts override takes; takes inform.

---

## Conventions

- **Wikilinks:** `[[path/to/article]]` without `.md` extension, relative to `knowledge/`.
- **Writing style:** encyclopedia-style, factual, third-person where appropriate.
- **Dates:** ISO 8601 (`YYYY-MM-DD` for dates, full ISO for timestamps in `log.md`).
- **File naming:** lowercase, hyphens for spaces (e.g. `auth-jwt-gotchas.md`).
- **Frontmatter:** every article has at minimum `title`, `sources`, `created`, `updated`.
- **Sources:** always link back to the `daily/` or `raw/` files that contributed.
- **Language:** match the source language; the compiler does not translate by default.

---

## Where to look next

This file is the agent-facing schema reference — loaded into every compile prompt as `${agents_md}`, so it stays lean on purpose. The full operator-side reference ships into the vault on every `wiki update` and lives at `<vault>/.wiki/docs/`. Read locally — no network round-trip:

- **Operations** (`compile` / `query` / `lint` / `ingest` / `collect` commands, the curiosity loop, audio-ingest fallback chain) — [`.wiki/docs/cli.md`](.wiki/docs/cli.md) and [`.wiki/docs/PROCESS.md`](.wiki/docs/PROCESS.md).
- **Collector inventory** (which substrate sources, what they read, where they write, piggyback cadence) — [`.wiki/docs/FEATURES.md`](.wiki/docs/FEATURES.md) "Registry-discovered Collectors" table. Authoritative runtime enumeration: `wiki collect --list`.
- **Configuration** (every `<vault>/.wiki/config.yaml` key with its dataclass default and rationale) — [`.wiki/docs/config.md`](.wiki/docs/config.md).
- **Engine layout** (`<vault>/.wiki/` directory map — `scripts/`, `prompts/`, `hooks/`, `lib/`) — [`.wiki/docs/engine-layout.md`](.wiki/docs/engine-layout.md).
- **Per-collector setup recipes** — [`.wiki/docs/setup-voice.md`](.wiki/docs/setup-voice.md), [`.wiki/docs/setup-pictures.md`](.wiki/docs/setup-pictures.md), [`.wiki/docs/setup-gmeet.md`](.wiki/docs/setup-gmeet.md), [`.wiki/docs/setup-obsidian.md`](.wiki/docs/setup-obsidian.md).
- **Article-shape rationale** (two-layer State+Timeline pages, takes substrate, dream cycle) — the relevant `.wiki/prompts/compile_*.md` carries the compile-time semantics.
