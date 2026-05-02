---
name: Human vault UX — Dashboard, MOCs, statistics & graphical reports
description: Three-layer split (Dashboard.md / knowledge/index.md / MOCs/) so the vault becomes useful to the human, not just the agent. Surfaces compile-pipeline state, lint triage, top-concepts, and graphical reports (heatmap, growth curve, cost-over-time, link-density histogram, source-type distribution). Adopts proven patterns from the lx vault (QuickAdd, Pending-Review queue, PARA sections) and adds engine-specific instrumentation that lx can't have. Includes plugin set, dataview/bases queries, charts strategy, and required state-history layer.
type: research
origin: vault-observation
created: 2026-05-02
---

# Human Vault UX — Dashboard, MOCs & Graphical Reports

## TL;DR

The vault is currently agent-readable but human-thin. `knowledge/index.md` is a flat compile-target for LLM consumption, `templates/dashboard.md` has 4 dataview tables and stops there. Two reference points point at a richer layer: the **lx vault** (sister Obsidian vault on iCloud) ships a substantially richer dashboard with QuickAdd buttons, agent-output triage queues, PARA navigation and orphan-finding; and the **Obsidian community** has converged on Dataview + Bases (1.9.10+) + Homepage + MOCs as the standard human-navigation stack for LLM-wikis.

The proposal is a three-layer split:

| Layer | Audience | Form |
|---|---|---|
| `knowledge/index.md` | **Agent** | unchanged — flat compile-target index |
| `Dashboard.md` (vault root) | **Human** | rich Homepage with pipeline status, lint triage, top-concepts, recents, growth charts |
| `knowledge/MOCs/<topic>.md` | **Human** | curated topic hubs — prose + `[[wikilinks]]`, not bare lists |

Plus a **statistics layer** (`Reports.md` or section in Dashboard) with graphical charts driven by Dataview / `obsidian-charts` / `obsidian-tracker` / `heatmap-calendar`, fed by a new append-only `state.history.json` that compile/flush write to.

This file is the design sketch. M003-shaped, slice candidates listed at the end.

---

## 1. Why now

- Round-1 (M001/M002) shipped the engine + Mailbox collector. The pipeline works; the **output is invisible to the human** unless they grep `knowledge/`.
- `concept.md:143` already names `daily/` as "episodic memory" — that's machine semantics. There's no equivalent declared layer for **the human reader's view** of the same data.
- The connection-quality backlog (`backlog/connection-quality.md`) recommends MOCs as one of five fixes for sparse graphs. MOCs are a human-curation surface, so they belong in this proposal too — not a separate slice.
- We have rich, structured data nobody sees: `state.json:total_cost`, `state.json:ingested[].hash`, `health.py:daily_activity`, `lint.py` issues, `count_inbound_links()`. A dashboard that surfaces these turns "I ran a flush" into measurable progress.

---

## 2. What lx vault does (reference implementation we can borrow from)

`/Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/lx/🗺️ Dashboard.md`. Key sections worth lifting:

| lx pattern | Why it applies here |
|---|---|
| **QuickAdd buttons** (typed-note creation: Notiz, Idee, Meeting, Briefing) | We have a similar typology in AGENTS.md (`type: article \| paper \| note \| transcript`). One-click "new note with right frontmatter" is faster than copy-template. |
| **Pending Review queue** (`status = "review"` dataview) | Agent-output triage — exactly maps to our `inbox/` flow. |
| **Inbox triage table** (type / agent / mtime) | Direct equivalent for `inbox/` after classifier. |
| **TASK queries** (`TASK WHERE !completed`) | Daily logs and notes will accumulate checkboxes; centralizing them as a triage list is free. |
| **Active Briefings** (`type = "briefing" AND status != "done"`) | Maps to our future agent-job pattern; placeholder for now. |
| **Orphan finder** (`length(file.inlinks) = 0` with folder excludes) | Already a lint check, but seeing it on the homepage drives action; lint output is read once per week, dashboard is read every session. |
| **PARA sections** (Company / AI / Personal) | We don't use PARA, but the equivalent split is `raw/` substrate types — useful for "show me all email-derived knowledge this week". |
| **Quick-Access link bar** | Cheap UX win. |

Plugins lx uses: `tasks`, `kanban`, `dataview`, `homepage`, `quickadd`, `buttons`. We have `dataview` + `excalidraw`. Delta:

- `homepage` — auto-open Dashboard.md on vault start. Tiny cost, big perception win.
- `bases` — built-in since 1.9.10, no install.
- `tasks` — only if we start emitting `- [ ]` checkboxes from compile (suggestion follow-ups, lint warnings).
- `quickadd` + `buttons` — only if user creates notes by hand often. For an agent-driven vault probably overkill in P1.

---

## 3. What's unique to llm-wiki (the "intelligent" bit lx can't replicate)

lx is a hand-written PKM. We have a **compile pipeline** with measurable state. The dashboard's signature feature should be **pipeline observability**:

| Signal | Source | Dashboard surface |
|---|---|---|
| Pending compiles | `list_raw_files()` ∖ `state.ingested` | "12 sources awaiting compile" + table |
| Failed flushes | `scripts/failed-flushes/*.md` | "3 retries pending" callout |
| Last compile timestamp | newest `mtime` in `knowledge/` | "Last compiled: 2h ago" |
| Total LLM spend | `state.total_cost` | "$12.34 lifetime, $0.42 today" — needs history |
| Lint queue size | `lint.py` issue count by severity | Triage list, click-through to fix |
| Top concepts | `count_inbound_links()` per article | "Most-linked: \[\[ai-coding-agents\]\] (24)" |
| Hottest week | `state.history.json` deltas | growth chart |
| Orphan rate | orphans / total articles | "Orphan rate 7.8% (target <5%)" |
| Connection density | edges / nodes from graph | "5.7 links/article" — flag if drifting down |
| Cost per article | total_cost / article count | "$0.18 / article" — sanity check |
| Source-type distribution | frontmatter `type:` aggregated | pie chart |
| Compile latency | per-file timing in history | bar chart, last 14 days |

**Unique angle:** the dashboard reads as a **build pipeline status page**, not just "recent notes". That's the engine showing its work.

---

## 4. Three-layer architecture

### 4.1 `knowledge/index.md` (unchanged)

Stays agent-facing. The compiler maintains it, the LLM reads it for navigation. No human attempts to make it pretty.

### 4.2 `Dashboard.md` at vault root (new — replaces / extends `templates/dashboard.md`)

Sections, top → bottom:

1. **Engine status callout** (one-line callout each, color-coded):
   - 🟢/🟡/🔴 pipeline (pending compiles count)
   - 🟢/🟡/🔴 retries (failed-flush count)
   - 🟢/🟡/🔴 lint (warning count)
   - $ spend today / lifetime
2. **Quick-Access bar** — links to `knowledge/index`, `Reports`, top 5 MOCs, AGENTS.md
3. **Pending Review** — articles where compiler flagged human-decision (e.g. `status: needs-review`, future field)
4. **Triage queues** (collapsible callouts):
   - Orphan articles (knowledge with 0 inlinks)
   - Stale articles (source hash drift)
   - Missing backlinks (one-way links)
   - Failed flushes (with retry button → command palette)
5. **Recently compiled** (last 15) — mtime, folder, source-count
6. **Recent daily logs** (last 7) — clickable, with session count per day
7. **Top concepts** (by `count_inbound_links`, top 10) — these are your knowledge hubs
8. **By substrate** (mini sections per `type:`) — articles, notes, transcripts, papers, MOCs
9. **Footer** — link to Reports.md, AGENTS.md schema, last compile timestamp + cost

### 4.3 `knowledge/MOCs/<topic>.md` (new layer)

Maps of Content. **Human-readable topic hubs**, not flat lists. Format:

```markdown
---
type: moc
tags: [topic-slug]
sources: []   # MOCs aren't compiled FROM raw, they curate knowledge
updated: 2026-05-02
---

# AI Coding Agents — MOC

Short prose framing why this topic matters and how the articles relate.

## Core concepts
- [[knowledge/concepts/agentic-loop]] — the inner cycle
- [[knowledge/concepts/tool-use]] — the I/O surface
- ...

## Open questions
- [[knowledge/questions/sleeper-token-bug]]

## Related MOCs
- [[knowledge/MOCs/local-llm]]
```

Two creation paths (decision needed):

- **Manual.** User creates 5–10 MOCs over time as topics emerge. Cheap, slow, requires discipline.
- **LLM-suggested.** New compile stage: cluster `knowledge/concepts/` by tag/embedding, propose MOC drafts, user approves. Costs more but compounds.

Recommendation: **start manual** (P1 has no LLM cost), add the suggestion stage in a later milestone if MOCs prove valuable.

---

## 5. Reports & graphical statistics

Either a dedicated `Reports.md` or a section in `Dashboard.md`. Charts via:

| Plugin | What it does | Use cases |
|---|---|---|
| `obsidian-charts` | Chart.js — line, bar, pie, radar, doughnut | Cost-over-time, articles-per-week, source-type pie, link-density histogram |
| `obsidian-tracker` | Time-series from frontmatter / regex / dataview | Daily-flushes trend, query-count trend, cost-per-day |
| `heatmap-calendar` | GitHub-style activity calendar | Daily-log activity, compile frequency |
| Mermaid (built-in) | Gantt, pie, xychart-beta, timeline | Roadmap visuals, milestone timelines |
| Excalidraw (already installed) | Curated static visuals | Architecture, concept maps |
| Bases (built-in 1.9.10+) | Card / table layouts on frontmatter | Filterable knowledge browser, kanban-style status board |

### 5.1 Charts proposed (P1 ≈ free, P2 ≈ needs history layer)

**P1 — single-snapshot (no history needed):**

1. **Source-type distribution** (pie). Aggregate `type:` field across `knowledge/`. Reveals whether the wiki skews toward articles vs notes vs transcripts.
2. **Tag frequency** (bar, top 20). Aggregate `tags[]`. Shows current focus areas.
3. **Articles by inbound-link bucket** (histogram, e.g. 0 / 1–2 / 3–5 / 6–10 / 11+). Visualizes the "everyone has a long tail of orphans" phenomenon. Threshold for action.
4. **Articles per folder** (bar). `concepts/`, `connections/`, `entities/`, `MOCs/`, ...
5. **Daily-log activity heatmap** (calendar). Files in `daily/` per day, last 90 days. GitHub-contribution feel.

**P2 — time-series (needs `state.history.json`):**

6. **Cumulative articles over time** (line). Article count weekly.
7. **Cumulative LLM spend** (line, $). Total cost weekly.
8. **Cost per article over time** (line, $). Efficiency curve — should bend down as cache hits accumulate.
9. **Compile throughput** (bar, daily). Sources compiled per day.
10. **Orphan rate over time** (line, %). Should trend ≤5%.
11. **Link density over time** (line, edges / node). Should trend up; flat = compile prompt is timid.

### 5.2 Required data layer change

Current `state.json` is **point-in-time** — it overwrites itself. For time-series we need an **append-only log**. Two options:

- **`state.history.jsonl`** — one JSON line per compile / flush event. Schema: `{ts, event, source, articles_changed, tokens, cost, lint_warnings, total_articles}`. Cheap to read with Tracker.
- **Frontmatter on each article: `compile_history: [{ts, tokens, cost}]`** — distributes the data, dataview can aggregate. Heavier but co-located with the artifact.

Recommendation: **`state.history.jsonl`** in P2. Single append from `compile.py`, single append from `flush.py`. Total diff ≈ 30 lines. Tracker reads JSONL natively (or a small `scripts/history.py` that reformats to a temp dataview-friendly file).

---

## 6. Plugins to add

| Plugin | Priority | Cost | Why |
|---|---|---|---|
| `homepage` | P1 | free | Auto-open Dashboard.md on vault start. Singular UX upgrade. |
| `obsidian-charts` | P1 | free | All P1 charts. Chart.js syntax in fenced ```chart blocks. |
| `heatmap-calendar` | P1 | free | Daily-activity calendar. Most visually striking single chart for low effort. |
| Bases | P1 | built-in 1.9.10+ | Filterable card/table view of `knowledge/` — replaces some dataview tables with native UI. |
| `obsidian-tracker` | P2 | free | Time-series after `state.history.jsonl` exists. |
| `tasks` | P2 | free | Only if compile starts emitting `- [ ]` follow-ups. |
| `iconize` | P3 | free | Folder icons. Pure cosmetics — schedule when bored. |
| `quickadd` | P3 | free | Only if user starts hand-creating typed notes. Currently agent does it. |
| `buttons` | P3 | free | Pairs with quickadd. |

Update `templates/.obsidian/community-plugins.json` once plugins land.

---

## 7. Pipeline integration (engine-side changes)

Things compile.py / flush.py / lint.py need to do that they don't today:

1. **`state.history.jsonl` append**. New helper `append_history(event, **fields)` in `utils.py`. Called from compile (after each file) and flush (after `append_to_daily`).
2. **`compile_cost` and `compile_ts` per article frontmatter**. Optional. Lets dataview show cost-per-article without history. Minor compile.py change to merge into output frontmatter.
3. **`needs_review: true` frontmatter flag**. Compiler sets when LLM is uncertain (low confidence, conflict with existing article). Drives the Pending Review section. Schema addition to AGENTS.md.
4. **`MOCs/` directory recognized in lint**. Update `list_wiki_articles()` to include it; `connections/`-style treatment.
5. **Health-CLI parity in dashboard**. `health.py:daily_activity` already produces sparklines for terminal. Same data should emit a Tracker-readable feed for the calendar heatmap.

Surface for the slice plan, not full implementation.

---

## 8. Open questions (need office-hours / user input)

1. **MOC creation: manual vs LLM-suggested in v1?** Recommendation: manual. User overrides if they want suggestions earlier.
2. **Reports.md: separate file or section in Dashboard?** Recommendation: section in Dashboard for P1 (5 charts), split out when content > one screen.
3. **Bases vs Dataview: kill the duplicates?** Recommendation: keep both. Bases for the filterable knowledge browser; Dataview everywhere else (more flexible, our queries already work).
4. **`state.history.jsonl`: how far back to backfill?** Recommendation: don't backfill. History starts the day this lands. Cumulative numbers can use point-in-time `state.json` as anchor.
5. **`Dashboard.md` vs `🗺️ Dashboard.md` (lx-style emoji prefix)?** Cosmetic — emoji helps in mobile sidebar but breaks shell paths. Recommendation: plain `Dashboard.md`, override-able per install.
6. **Mobile UX.** Dataview / charts / heatmap-calendar all render on Obsidian Mobile but slowly. Should we have a `Dashboard-mobile.md` lite variant? Probably P2 question.
7. **Costs.** No new LLM cost in P1 (all queries are local Dataview). P2 adds optional MOC-suggestion compile pass. P1 is essentially **free + plugins**.

---

## 9. Slice candidates (when this becomes M003)

Sketch — not a commitment.

- **S01 — Dashboard scaffold.** New `Dashboard.md`, basic engine-status callout (counts only, no charts), Quick-Access bar, recently-compiled / recent-daily / top-concepts dataview tables. Install `homepage` plugin in `community-plugins.json`. Document in PROCESS.md.
- **S02 — Lint triage queues.** Surface `lint.py` warnings on Dashboard as collapsible sections (orphans / stale / missing-backlinks / failed-flushes). One callout per category with click-through.
- **S03 — Charts P1.** Install `obsidian-charts` + `heatmap-calendar`. Add 5 charts: source-type pie, tag-frequency bar, inbound-link histogram, articles-by-folder bar, daily-activity heatmap. All single-snapshot, no history layer.
- **S04 — MOC layer (manual).** New `knowledge/MOCs/` directory + AGENTS.md schema for MOC type. Seed 2–3 hand-written MOCs as proof. Add MOCs section to Dashboard.
- **S05 — `state.history.jsonl` + Tracker charts.** New history layer in `utils.py`. Wire compile.py / flush.py to append. Install `obsidian-tracker`. Add P2 charts: cumulative articles, cumulative cost, cost-per-article, compile throughput, orphan rate, link density.
- **S06 — Bases knowledge browser.** Native filterable knowledge browser with type / tag / status facets. Replace one or two dataview tables with Bases for comparison.
- **S07 (deferred to M004?) — LLM MOC suggestions.** New compile stage that proposes MOC drafts from clusters. Human-approval gate.

S01–S04 ≈ M003. S05–S06 likely M004. S07 is a later milestone.

---

## 10. References

- lx vault dashboard — `/Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/lx/🗺️ Dashboard.md`
- Obsidian Bases vs Dataview cheat sheet — Lennart, Medium, 2026
- ObsidianMOC repo — seqis, MOC management guide
- Karpathy's LLM Wiki gist — `gist.github.com/karpathy/442a6bf...`
- Connection-quality synthesis — `.ytstack/backlog/connection-quality.md` (related — MOCs are one of the 5 fixes there too)
- Top Obsidian Plugins 2026 — Sébastien Dubois
