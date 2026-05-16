# Areas — 7th knowledge bucket for ongoing responsibilities

`knowledge/` currently splits by entity-type: `concepts`, `projects`, `people`, `facts`, `MOCs`, `qa`, `connections`. Missing: **Areas** — ongoing responsibilities without an end-state. Adopted from PARA's Areas tier (the second of two PARA ideas worth lifting — see `archives-flag.md` for the first). Surfaced during `lx-vault-merge.md` audit.

## The gap

Today, "Yesterday CEO-Hat", "llm-wiki Maintenance", "Personal Health Tracking", "Apartment Logistics" have no home:

- `projects/` is wrong — projects have deadlines and end-states. CEO-Hat doesn't.
- `concepts/` is wrong — concepts are abstract knowledge. Areas are roles/responsibilities, time-bounded only by "as long as I have this role".
- `people/` is wrong — Areas may involve people but aren't *about* a person.
- `facts/` is wrong — facts are atomic claims, not responsibility containers.

Result today: these get force-fit into `projects/` (then never close), or they don't exist in the wiki at all and live in head / scattered notes. The `lx/` audit found 6+ clear Areas in `🌈 Company/Areas/` + `👤 Personal/Areas/` that would import as Areas, not Projects.

## The pattern

New folder `knowledge/areas/` with this shape (composes with entity-pages-State+Timeline once that ships):

```yaml
---
title: "llm-wiki Maintenance"
type: area
domain: meta  # optional, see domain-frontmatter.md
status: active  # active | dormant | retired
last_synthesized: 2026-05-16
---

# llm-wiki Maintenance

> One-paragraph: what this responsibility covers, why it exists, who else (if anyone) shares it.

## Current State
- **Cadence:** ad-hoc compile/flush runs, weekly review
- **Active surfaces:** dashboard, daily-rollup digest
- **Health:** green (last broken pipeline: 2026-04-29)

## Open Threads
- Migrate lx vault → lxw (this backlog)
- Decide on archives-flag schema

## Action Items
- [ ] Ship archives-flag v1 📅 2026-06-01
- [ ] Run weekly priority sweep

## Related
- [[knowledge/projects/m005-personal-tasks]]
- [[knowledge/projects/m006-calendar-collector]]

---

## Timeline
- **2026-05-15** | M005 closed
- **2026-05-13** | scripts/ reorg shipped
```

Key differences from `projects/`:
- `status: active|dormant|retired` (not `status: planning|in-progress|done`)
- No deadline frontmatter
- Open Threads are first-class (Areas accumulate them indefinitely; Projects close them)
- Retired ≈ archived (composes with `archived-flag.md`)

## Why it matters now

- M005 shipped Open Threads + Action Items but they currently land on Project pages or Person pages. There's no home for threads tied to a *role* (e.g. "as CEO, I'm waiting on...")
- Without Areas, the wiki under-represents ongoing work. Projects close, are archived, the work continues as Area but the wiki loses the thread.
- Should ship **before** lx-merge entity-pages migration — otherwise 6+ Area-candidates land in `projects/` and need second migration.

## Open design questions

- **Single `status` axis or split?** `active|dormant|retired` is minimal. Alternative: separate `active: bool` + `archived: bool` (composing with archives-flag). Recommend single enum for clarity; `retired` ≈ `archived: true` at the schema-validator level.
- **Areas with sub-Projects** — a "Yesterday CEO-Hat" Area might reference "Q3 fundraise" Project. Just wikilinks, or explicit `parent_area: yesterday-ceo` frontmatter on the Project? Wikilinks suffice v1; revisit if multiple Areas want filtered Project rollups.
- **Compile-loop interaction** — does compile re-synthesize Area State blocks from substrate (daily mentions, meeting transcripts) the way it does for Projects/People? Yes, via entity-pages mechanism once that lands. Standalone v1: Areas are operator-written, no auto-compile.
- **MOC inclusion** — Area pages should appear in domain MOCs (`MOCs/yesterday.md` should list "Yesterday CEO-Hat" Area alongside Projects). One-liner change to MOC generator.
- **Dashboard treatment** — Areas pane on dashboard? Or only their aggregated Open Threads bubble up via existing M005 surfaces? Probably the latter — don't multiply surfaces.

## Touchpoints

- `knowledge/areas/` — new folder, add to `seed`/template
- `scripts/core/frontmatter.py` — add `type: area`, `status: active|dormant|retired` enum
- `scripts/facts/moc.py` — include `areas/` in domain-MOC auto-aggregation
- `scripts/dashboard/personal_tasks.py` (or wherever M005 Open Threads aggregates) — include Areas as a source-type for Open Threads/Action Items
- `scripts/cli.py` — `wiki query --type area` works automatically if query is type-aware; verify
- `scripts/lint.py` — type-conditional checks (Areas need `status`, no `deadline`)
- `prompts/compile_main.md` — area branch in entity-pages prompt (deferred to entity-pages milestone)
- `AGENTS.md` + `templates/AGENTS.example.md` — document Areas alongside the other 7 types
- `templates/.obsidian/graph.json` — color rule for `type: area` (suggest: teal, distinct from projects/cyan and concepts/indigo per `project_graph_view_palette`)

## Lift estimate

- Schema + folder + frontmatter recognition: 0.5 day
- MOC + dashboard inclusion: 0.5 day
- Lint type-conditional: 0.25 day
- Migration of 6-10 force-fit Project pages → Areas (find them, re-frontmatter): 0.5 day
- Graph view color: 0.25 day

**~2 days end-to-end** for the bucket. Entity-pages compile branching for Areas adds ~0.5 day on top of the entity-pages milestone.

## Risks

1. **Over-classification** — operator can't decide if "Yesterday Fundraise" is Project or Area. Mitigation: rule of thumb in AGENTS.md ("has a finish line → Project; ongoing → Area; if both, the Area owns the long-term, the Project owns the current push"). Acceptable ambiguity.
2. **Empty bucket** — operator doesn't actually use Areas, they sit as 0-3 files. Test by seeding 5 obvious Areas at ship-time (CEO-Hat, llm-wiki Maintenance, Personal Health, Apartment, Family); if those don't accrete content over 4 weeks, Areas was wrong call. Cheap to delete the folder if so.
3. **Areas + Projects redundancy on dashboard** — both surface Open Threads. Risk: duplicate items if the same thread is on both. Mitigation: thread-id deduplication (already needed for M005).

## Ripens when

- Now. Independent of lx-merge timing; lx-merge surfaces 6+ Area candidates that would benefit but the gap exists without them.
- Should ship **before** the entity-pages-anchored phase of lx-merge to avoid double migration.

## Status

**SHIPPED** via M008 (3a445b7, 2026-05-16, Agent A). See commit message + git log for implementation details. Backlog kept as decision-context.