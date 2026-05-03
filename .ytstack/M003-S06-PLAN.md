---
milestone: M003
slice: S06
project: llm-wiki
created: 2026-05-03T01:15:00Z
status: planned
task_count: 2
completed_tasks: 0
---

# M003-S06 — Slice Plan

**Goal:** Native Obsidian Bases (built-in 1.10+) view of `knowledge/` as a filterable table. Operator gets a knowledge browser without writing dataview queries: 2 default views (all-knowledge sorted by mtime, by-type grouped). Dashboard surfaces the Base via embed.

**Out of scope:** custom card layouts, formulas, extended schemas. v1 is read-only browse with mtime-sort.

## Architectural decisions baked in

- **Single `.base` file at vault root**: `knowledge.base`. Operator can duplicate + customise; the seed remains canonical.
- **Filter scope**: `file.folder.startsWith("knowledge")` AND exclude `index.md` + `log.md`. Same pattern as the dataview queries in the existing dashboard sections.
- **Two views, not one**: "All" (flat list, mtime-sorted desc) + "By type" (grouped). More complex view shapes come per-vault as operator preference.
- **Dashboard embed**: not a section unto itself — Bases embed is heavy. Add a small "## 🗃 Browse knowledge" section with a `[[knowledge.base]]` wikilink, optionally an embed `![[knowledge.base]]`. Keep dashboard render snappy.
- **Seed via the same `_seed_file` mechanism** used for AGENTS.md / dashboard.md. Additive (preserves operator's customised .base).

## Tasks

- [ ] T01 — Create `templates/knowledge.base` (YAML — filter on `knowledge/`, two views: "All" sorted by `file.mtime` desc, "By type" grouped). Extend `lib/seed.sh:seed_vault_templates` step 2-ish to seed it into `target/knowledge.base` (additive). Done when the file exists and `seed_vault_templates` against a tmp vault places it at the target. No live verification possible without an Obsidian render — defer that to manual smoke in T02.

- [ ] T02 — `templates/dashboard.md` gains `## 🗃 Browse knowledge` section between `## 🔧 Run` and `## 🤖 Agents` with a `[[knowledge.base]]` wikilink + small description. Add `### Bases-Browser` subsection to `docs/PROCESS.md` §12. Manual smoke note appended to S06-PLAN. Run full suite. Close S06 in roadmap. Done when grep finds the new section, suite green, ROADMAP shows S06 [x].

## Done when

Both tasks marked `[x]`. M003 exit criterion #8 (Bases view as filterable knowledge browser) satisfied. M003 milestone complete: 6/7 slices (S03 stays reserved/optional).

## Notes

(Fill during execution.)

## Notes (T02, 2026-05-03)

- 70 pytest tests green (no new tests in this slice — Bases is operator-facing UI; YAML is verified by Obsidian itself).
- T01 subprocess smoke verified `seed_vault_templates` copies `knowledge.base` cleanly.
- Live Obsidian smoke deferred until lxw `wiki update`. Once that runs:
  - `wiki seed` puts `knowledge.base` at vault root.
  - Dashboard "🗃 Browse knowledge" wikilink opens the Base.
  - Two views (All / By type) should render the 470 articles in lxw `knowledge/`.
- Schema chose mtime DESC + limit 200 to avoid laggy initial render on large vaults. Operator can edit views in-place — seed is additive.
- Decision baked: NO embed (`![[knowledge.base]]`) in Dashboard. Bases render is heavier than Dataview; Dashboard stays snappy with a wikilink instead. Operator can add an embed if they want one.
