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

> **EDIT THIS SECTION.** Replace with your own context — name, role, current projects, products, the people and entities you collaborate with. The compiler uses this to disambiguate references and maintain `knowledge/people/` + `knowledge/projects/` consistency.

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
│   ├── youtube/     # Collector: video metadata + transcript + comments (per-video markdown)
│   └── health/      # Collector: daily biometric rollup (Oura) — `<year>/<date>--<account>.md`
├── transcripts/     # PERMANENT: meeting + audio transcripts
│   ├── jamie/       # Collector: Jamie AI meeting-notetaker (paired summary + diarised transcript)
│   └── gmeet/       # Collector: Gemini Meet Notes + Transcript Docs (Drive API; paired sections)
├── voice/           # PERMANENT: dictation transcripts (collectors/voice.py — folder-watch on personal.voice_inbox)
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
    └── email.md               ← collectors/email_collector.py — delta links
```

**Subfolder (`daily/<date>/<source>.md`)** — append-only captures owned by exactly one writer each. All five writers go through `core.daily_capture` (fcntl-flocked, source-name validated against `KNOWN_SOURCES`). Failures in the rollup write never break the primary substrate write — they're side-effects on top.

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
└── MOCs/             # Curated topic hubs (human-curated)   (type: moc)
```

Each article in `knowledge/` carries this YAML frontmatter:

```yaml
---
title: "Article Title"
type: concept | connection | qa | person | project | area | moc | fact
compiled_from: "raw/articles/some-source.md"   # or list[] for multi-source
created: 2026-04-01
updated: 2026-05-02
tags: [topic1, topic2]
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

Cross-cutting synthesis linking 2+ concepts. Created when a source reveals a non-obvious relationship.

```markdown
---
title: "Connection: X and Y"
connects:
  - "concepts/concept-x"
  - "concepts/concept-y"
sources:
  - "daily/2026-04-04.md"
created: 2026-04-04
updated: 2026-04-04
---

# Connection: X and Y

## The Connection

[What links these concepts]

## Key Insight

[The non-obvious relationship discovered]

## Evidence

[Specific examples]

## Related Concepts

- [[concepts/concept-x]]
- [[concepts/concept-y]]
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

---

## Core Operations

### 1. Compile (`daily/` + `raw/` → `knowledge/`)

When processing a source file:

1. Read the source file.
2. Read `knowledge/index.md` to understand the current state.
3. Read existing articles that may need updating.
4. For each piece of knowledge found:
   - If an existing article covers it: **UPDATE**, add the source to the frontmatter.
   - If it's new: **CREATE** a new article in the appropriate subdirectory.
5. If a non-obvious connection between 2+ concepts surfaces: CREATE a `connections/` article.
6. If a person is mentioned significantly: CREATE or UPDATE a `people/` article.
7. If a project is discussed: CREATE or UPDATE a `projects/` article.
8. **UPDATE** `knowledge/index.md`.
9. **APPEND** to `knowledge/log.md`.

**Guidelines:**

- A single source may touch 5–15 knowledge articles.
- Prefer updating existing articles over creating near-duplicates.
- Use `[[wikilinks]]` with paths relative to `knowledge/` (e.g. `[[concepts/slug]]`).
- Write in encyclopedia style — factual, concise, self-contained.
- Every article has YAML frontmatter and links back to its source files.

### 2. Query (Ask the Knowledge Base)

1. Read `knowledge/index.md`.
2. Identify 3–10 relevant articles based on the question.
3. Read those articles in full.
4. Synthesize an answer with `[[wikilink]]` citations.
5. If `--file-back`: create a `knowledge/qa/` article and update index + log.

**Why no RAG:** at personal scale (50–500 articles), the LLM reading a structured index outperforms cosine similarity. The LLM understands what the question is really asking and selects pages accordingly.

### 3. Lint (Health Checks)

Seven checks:

1. **Broken links** — `[[wikilinks]]` pointing to non-existent articles.
2. **Orphan pages** — articles with zero inbound links.
3. **Orphan sources** — `daily/` or `raw/` files not referenced by any article.
4. **Stale articles** — source changed since article was last compiled.
5. **Contradictions** — conflicting claims across articles (LLM judgment).
6. **Missing backlinks** — A links to B but B doesn't link back.
7. **Sparse articles** — below the configured threshold (`limits.sparse_threshold_words`), likely incomplete.

### 4. Ingest (Manual Source Addition)

For non-conversation sources (articles, audio, PDFs, notes):

1. Place the source in the appropriate `raw/` subdirectory with frontmatter.
2. For audio: transcribe via Whisper (API or local), save transcript to `raw/transcripts/`, audio to `raw/audio/`.
3. Trigger compilation of the new source.

### 5. Collect (Substrate Sources → `raw/`)

Substrate collectors extract metadata or transcripts from local apps + APIs without reading user content beyond what each substrate's mandate covers. They produce structured input the compiler turns into knowledge articles. All ten ride the Collector Registry (`scripts/collectors/base.py`); operator invocation via `wiki collect <name>`; piggyback-eligible collectors auto-run after `compile_after_hour`.

| Collector | Source | Output | Trigger |
|---|---|---|---|
| `email` | Mailbox via adapters (Thunderbird mbox, Gmail API, generic IMAP) — multi-tenant per `personal.accounts.<id>.reader` | `raw/notes/email/<account>-<date>.md` (full) + `<account>-delta-<ts>.md` (incremental) | piggyback 24 h |
| `jamie` | Jamie AI tRPC API — multi-tenant per `personal.accounts.<id>.jamie` (kind: `jamie-api`) | `raw/transcripts/jamie/<date>--<slug>--<id>.md` — summary + speaker-diarised transcript + action items | piggyback 6 h |
| `gmeet` | Google Drive API v3 (`drive.meet.readonly`) — Gemini Meet Notes + Transcript Docs, multi-tenant per `personal.accounts.<id>.gmeet` | `raw/transcripts/gmeet/<date>--<slug>--<meeting-key>.md` — paired `## Summary` + `## Transcript` sections | piggyback 6 h |
| `voice` | Folder-watch on `personal.voice_inbox` — `.txt` / `.md` from any dictation tool (iOS Shortcut → iCloud Drive recommended; OpenWhispr / FluidVoice / macOS dictation as alternatives) | `raw/voice/voice-<date>-<HHMM>-<slug>.md` | piggyback 1 h |
| `health` | Oura REST API (per-account PAT) — multi-tenant per `personal.accounts.<id>.health` (kind: `oura-pat`) | `raw/notes/health/<year>/<date>--<account>.md` — sleep / readiness / HRV / steps / resting HR; `sensitivity: high` | piggyback 24 h |
| `screenshots` | `~/Screenshots/` PNG files via local Vision LLM (gemma4 over Ollama) | per-PNG sidecar `.md` at `~/Screenshots/<file>.md` + 384 px thumb + batch report in `raw/notes/screenshots/` | piggyback 24 h |
| `calendar` | Thunderbird calendar SQLite (Google Calendar sync) | `raw/notes/calendar/calendar-overview-<date>.md` — event categories, attendees, time allocation | `wiki collect calendar` |
| `browser` | Firefox `places.sqlite` + STG backups + Chrome bookmarks/history | `raw/notes/browser/browser-overview-<date>.md` — tab clusters, bookmark taxonomy, visit patterns | `wiki collect browser` |
| `tabs` | Firefox Simple Tab Groups (STG) backup directory | `raw/notes/browser/tab-groups-overview-<date>.md` — active groups + tab URLs/titles | `wiki collect tabs` |
| `youtube` | yt-dlp + youtube-transcript-api + comments + optional ffmpeg frames (gemma4 Vision) | `raw/notes/youtube/<channel>--<title>--<vid>.md` — tiered: 0=meta, 1=+transcript, 2=+comments, 3=+visual | `wiki collect youtube` / `wiki ingest-youtube` |

Discovery + dispatch: `wiki collect --list` enumerates everything registered above. Source-of-truth lives in `scripts/collectors/` (engine repo) — this table is the operator-facing orientation, kept in sync via `docs/setup-voice.md`-style per-collector setup docs in the engine repo.

Collectors extract **metadata or substrate transcripts only** — no email bodies, no page content, no credentials. Output files use the standard `raw/` frontmatter with `type: note` and `origin: <collector-name>`.

#### The Curiosity Loop

After each compilation, the compiler analyzes source content + wiki index for knowledge gaps and may auto-generate deep-scan requests, processed daily as a piggyback task.

```
Compiler processes source → wiki articles
       ↓
maybe_generate_curiosity_requests() runs (local Vision/Curiosity model via Ollama)
       ↓
Analyzes source + wiki index → identifies specific gaps
       ↓
Writes JSON request files to raw/requests/ (cap: limits.curiosity_max_gaps)
       ↓
Piggyback task: `wiki curiosity run-oldest` (daily, 24h cooldown) — dispatches by request kind
       ↓
Deep scan reads email bodies → thread reconstruction → LLM filtering
       ↓
Report to raw/notes/email/deep-*.md → next compile picks it up → gap closed
```

`raw/requests/` request files look like:

```json
// raw/requests/request-{slug}-{date}.json
{
  "type": "email-deep-scan",
  "status": "pending",
  "folder": "INBOX/Work",
  "account": "<account-id>",
  "model": "<curiosity-model>",
  "topic": "<short topic>",
  "rationale": "<why the compiler thinks this gap is worth investigating>"
}
```

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

## Audio Ingest

Fallback chain for transcription:

1. **OpenAI Whisper API** (preferred) — requires `OPENAI_API_KEY` in `.claude/.env`.
2. **Local whisper / whisper.cpp** — free, offline (`brew install whisper-cpp` or equivalent).
3. **Placeholder** — create article with `> TODO: transcribe`.

---

## Operational Layout (`.wiki/`)

All ops/tooling lives under `<vault>/.wiki/` (hidden from Obsidian's file tree). Content layers (`daily/`, `raw/`, `knowledge/`, `inbox/`) stay at root.

```
<vault>/
├── .wiki/
│   ├── wiki             ← entry-point CLI (interactive + scriptable)
│   ├── config.yaml      ← single source of truth for tunables
│   ├── lib/             ← bash modules
│   ├── scripts/         ← Python CLI tools (compile, flush, lint, scan-*, query, …)
│   ├── hooks/           ← agent session hooks
│   ├── prompts/         ← LLM prompts as standalone .md files
│   └── reports/         ← lint + review-wiki output
├── daily/, raw/, knowledge/, inbox/   ← user-visible content
├── AGENTS.md, README.md, dashboard.md, ...
└── .claude/, .obsidian/, .venv/, ...
```

## CLI Entry Point (`./.wiki/wiki`)

Single entry point for setup, config, and agent integration. Pattern: `wiki <command> [args]`.

| Command | Purpose |
|---|---|
| `wiki` | interactive top-level menu |
| `wiki setup` | first-time wizard: 5 config questions + hooks install |
| `wiki status` | full system status (config summary + hooks install table + Ollama probe) |
| `wiki config` | interactive config editor |
| `wiki config get KEY` | print one value, dot-notation (`models.compile_model`) |
| `wiki config set KEY VAL` | set + write back to `.wiki/config.yaml` |
| `wiki config keys` | list all settable keys |
| `wiki config wizard` | re-run the 5-question wizard |
| `wiki hooks install` | install hooks into agent configs (claude / codex / gemini / cursor) |
| `wiki hooks uninstall` | remove wiki-managed hook entries |
| `wiki hooks status` | install table |
| `wiki help` | usage |

## Configuration Layer (`.wiki/config.yaml`)

All tunable parameters live in `<vault>/.wiki/config.yaml` — single source of truth. Scripts load it at startup via `.wiki/scripts/wiki_config.py`. Defaults are baked into the dataclass so a missing or partial YAML is safe.

**Sections:**

- `scheduling` — `compile_after_hour`, `dedup_window_seconds`, `timezone`.
- `piggybacks` — per-task `enabled` + `cooldown_hours` (+ optional `max_per_run`).
- `models` — `compile_model` (Claude), `ollama_url`, `vision_model`, `curiosity_model`, `classify_model`.
- `limits` — compile caps, flush retries, screenshot constraints, curiosity bounds, lint thresholds.
- `features` — master switches: `curiosity_loop`, `vision_screenshots`, `procmail_execution`.
- `personal` — per-install operator data (account map, calendar keywords, Thunderbird/Firefox profile paths). Empty defaults; populate via `wiki setup` or by editing `config.yaml` directly.

**Inspection:** `uv run python .wiki/scripts/wiki_config.py` prints the resolved config.

**When adding a new tunable:** extend the matching dataclass in `wiki_config.py`, document it in YAML with a comment, replace the hardcoded constant in the script with `CONFIG.<section>.<field>`. Do **not** add ad-hoc constants back to scripts — extend the config layer.

## Prompts Layer (`prompts/`)

All LLM prompts live as standalone `.md` files under `<vault>/.wiki/prompts/`. Scripts load them via `prompts.render(name, **vars)`.

**Placeholder syntax:** `${var}` (chosen over Python's `{var}` so JSON/YAML examples in the prompt body can use literal `{` and `}` without escaping).

**Editing:** open the `.md`, edit, save — next script run picks it up. Missing files or undefined `${var}` placeholders raise `PromptError` so drift is loud, not silent.

**Do not** inline new prompt strings in scripts. Externalize to `prompts/` for consistency, easier review, and so you (or a future plugin) can tune without code edits.

---

## Full Project Structure

```
<vault>/
├── .claude/
│   ├── settings.json              # Hook configuration
│   ├── settings.local.json        # Personal permissions (gitignored)
│   ├── skills/                    # Symlinked from .wiki/skills/* by install.sh
│   └── .env                       # API keys (gitignored)
├── .gitignore
├── AGENTS.md                      # This file — schema + technical reference
├── README.md                      # User-facing documentation
├── dashboard.md                   # Obsidian home page (Dataview)
├── raw/                           # Curated sources (immutable)
│   ├── articles/, papers/, notes/{email,calendar,browser,tabs,screenshots,youtube,health}/
│   ├── transcripts/{jamie,gmeet}/, voice/, audio/
│   ├── memories/
│   ├── requests/                  # Compiler-generated ingest requests
│   └── suggestions/               # Compiler-generated optimization suggestions
├── daily/                         # Conversation logs (auto-captured)
├── knowledge/                     # Compiled knowledge (LLM-owned)
│   ├── index.md
│   ├── log.md
│   └── concepts/, connections/, qa/, people/, projects/, areas/, facts/, MOCs/
├── inbox/                         # Transient: drop files here for classification
└── .wiki/                         # Engine — installed by install.sh
    ├── wiki                       # CLI entry point
    ├── config.yaml                # Single source of truth (gitignored)
    ├── config.example.yaml
    ├── lib/, scripts/, hooks/, prompts/
    ├── skills/                    # Agent skills (vault-triage, ingest-audio, …)
    └── .venv/                     # Python venv (gitignored)
```
