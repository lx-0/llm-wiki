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
├── notes/           # PERMANENT: manually written notes, scanner outputs
│   ├── email/       # Scanner output: email metadata, deltas, deep scans
│   ├── calendar/    # Scanner output: calendar metadata
│   ├── browser/     # Scanner output: browser metadata
│   └── screenshots/ # Scanner output: screenshot descriptions (Vision LLM)
├── transcripts/     # PERMANENT: audio transcriptions (Whisper output)
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

### Layer 2: `daily/` — Conversation Logs (Immutable, Auto-Captured)

Auto-captured Claude Code session summaries. Append-only, never edited after creation.

```
daily/
├── 2026-04-08.md
├── 2026-04-09.md
└── ...
```

Each file follows this format:

```markdown
# Daily Log: YYYY-MM-DD

## Sessions

### Session (HH:MM) - Brief Title

**Context:** What the user was working on.

**Key Exchanges:**
- User asked about X, assistant explained Y

**Decisions Made:**
- Chose library X over Y because...

**Lessons Learned:**
- Always do X before Y to avoid...

**Action Items:**
- [ ] Follow up on X
```

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
├── facts/            # Hard facts (human-owned, override sources)  (type: fact)
└── MOCs/             # Curated topic hubs (human-curated)   (type: moc)
```

Each article in `knowledge/` carries this YAML frontmatter:

```yaml
---
title: "Article Title"
type: concept | connection | qa | person | project | moc | fact
compiled_from: "raw/articles/some-source.md"   # or list[] for multi-source
created: 2026-04-01
updated: 2026-05-02
tags: [topic1, topic2]
---
```

The `type:` field MUST match the destination folder. It is the single source of truth for substrate-type — Dataview queries, lint, dashboard charts, and the compile prompt all rely on it. Lint flags any article whose `type:` is missing or doesn't match its folder.

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

### 5. Scan (Local Data Sources → `raw/notes/`)

Scanner scripts extract metadata from local applications without reading content. They produce structured overviews that the compiler turns into knowledge articles.

| Script | Source | Output |
|---|---|---|
| `scan-email.py` | Thunderbird mailboxes | `raw/notes/email/` — sender/recipient stats, volume over time, folder structure |
| `scan-calendar.py` | Thunderbird calendar SQLite | `raw/notes/calendar/` — event categories, frequency, time allocation |
| `scan-browser.py` | Firefox + Chrome bookmarks/history/tabs | `raw/notes/browser/` — tab clusters, bookmark taxonomy, visit patterns, search topics |
| `scan-screenshots.py` | `~/Screenshots/` PNG files via local Vision LLM | per-PNG sidecar `.md` + batch report in `raw/notes/screenshots/` |

Scanners extract **metadata only** — no email bodies, no page content, no credentials. Output files use the standard `raw/` frontmatter with `type: note` and `origin: scan-{type}`.

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
Piggyback task: scan-email.py --follow-requests (daily, 24h cooldown)
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
│   ├── articles/, papers/, notes/, transcripts/, audio/
│   ├── memories/
│   ├── requests/                  # Compiler-generated ingest requests
│   └── suggestions/               # Compiler-generated optimization suggestions
├── daily/                         # Conversation logs (auto-captured)
├── knowledge/                     # Compiled knowledge (LLM-owned)
│   ├── index.md
│   ├── log.md
│   └── concepts/, connections/, qa/, people/, projects/
├── inbox/                         # Transient: drop files here for classification
└── .wiki/                         # Engine — installed by install.sh
    ├── wiki                       # CLI entry point
    ├── config.yaml                # Single source of truth (gitignored)
    ├── config.example.yaml
    ├── lib/, scripts/, hooks/, prompts/
    ├── skills/                    # Agent skills (vault-triage, ingest-audio, …)
    └── .venv/                     # Python venv (gitignored)
```
