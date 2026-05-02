---
milestone: M003
slice: S01
project: llm-wiki
created: 2026-05-02T16:58:33Z
status: done
task_count: 7
completed_tasks: 7
---

# M003-S01 — Slice Plan

**Goal:** `Dashboard.md` exists at vault root, opens automatically on vault start via the `homepage` plugin, and shows live engine-status (pending compiles, failed flushes, lint warnings, total LLM cost) plus recently-compiled articles, recent daily logs, and the top-10 most-linked concepts.

**Out of scope (deferred to later slices):** lint-triage queues (S02), charts (S03), MOCs section (S04), history-driven time-series (S05), Bases browser (S06).

## Architectural decisions baked in

- `state.json` lives at `.wiki/state/state.json` (engine, not vault). Obsidian/Dataview cannot read it directly. A new `scripts/dashboard-stats.py` will emit a vault-readable cache file `_dashboard-stats.md` at vault root with computed counts in frontmatter; Dashboard.md renders those via Dataview / inline-field references.
- The cache file is regenerated as a flush-piggyback (same pattern as `optimize-claude-md.py`, `scan-screenshots.py`, etc.).
- Filename: canonical `Dashboard.md` (capital D) at vault root. Replaces the existing thin `templates/dashboard.md`. Install.sh seeds `Dashboard.md`; existing `dashboard.md` (lowercase) on installed vaults is left alone — operator can manually migrate.
- `homepage` plugin config seeded in `templates/.obsidian/plugins/homepage/data.json` matches the shape used in lx vault (verified via inspection): `{value: "Dashboard", kind: "File", openOnStartup: true, openMode: "Replace all open notes"}`.

## Tasks

- [x] T01 — Seed `homepage` plugin in templates: add `"homepage"` to `templates/.obsidian/community-plugins.json`; create `templates/.obsidian/plugins/homepage/data.json` with `value: "Dashboard"`, `openOnStartup: true`, `openMode: "Replace all open notes"`. Done when fresh `install.sh` run on a clean target produces a `.obsidian/plugins/homepage/data.json` and the plugin appears in community-plugins.
- [x] T02 — Replace `templates/dashboard.md` with new `templates/Dashboard.md` (capitalized). Sections in order: (1) engine-status callout — Dataview inline-field block reading from `_dashboard-stats.md` frontmatter; (2) quick-access bar (`[[knowledge/index]] · [[AGENTS|Schema]]`); (3) Recently compiled (Dataview TABLE from `knowledge`, top 15, sort mtime desc); (4) Recent daily logs (Dataview TABLE from `daily`, top 7); (5) Top concepts (Dataview TABLE sorting by `length(file.inlinks)` desc, top 10, from `knowledge`); (6) footer with last-compiled timestamp + total cost. Done when Dashboard.md renders all sections in Obsidian without Dataview errors.
- [x] T03 — Implement `scripts/dashboard-stats.py`: reads `state.json` (`total_cost`), counts files in `failed-flushes/`, runs `lint.py --json` (or imports lint check functions directly), counts `list_raw_files()` minus `state.ingested` for pending compiles. Writes `_dashboard-stats.md` at vault root with frontmatter only: `pending_compiles`, `failed_flushes`, `lint_warnings`, `total_cost_lifetime`, `total_cost_today` (today comes from `state.history.jsonl` if exists, else null), `last_compile_ts`, `articles_total`, `daily_logs_total`. Runs as flush-piggyback (added to `flush.py` after `maybe_trigger_compile`). Done when `wiki flush` updates `_dashboard-stats.md` and a unit test verifies the file shape.
- [x] T04 — Update `install.sh`: copy `Dashboard.md` into vault root if absent (parallel to existing `dashboard.md` clause). Update `seed_obsidian()` to also copy the homepage `data.json`. Document the change in `install.sh` ok-message. Done when running install on a fresh target seeds Dashboard.md, plugin config, and Obsidian opens Dashboard.md on next launch.
- [x] T05 — Update `docs/PROCESS.md`: add a "Three-layer vault UX" section explaining Dashboard.md (human) vs `knowledge/index.md` (agent) vs `knowledge/MOCs/` (human-curated, lands in S04). Document `dashboard-stats.py` in the piggyback list. Done when `docs/PROCESS.md` has the new section and an internal doc-link from README.md (or AGENTS.md) points to it.
- [x] T06 — Interactive dashboard rebuild (lx-pattern, but Meta Bind instead of deprecated Buttons plugin). Capture buttons (Notiz / Idee / Frage / Meeting) → QuickAdd → typed-note templates land in `inbox/`. Inbox triage table, Pending review table, Open tasks (Tasks plugin), Orphan list at the bottom. Engine-managed substrates (`raw/` / `daily/` / `knowledge/` / `Templates/`) excluded from working-file queries. Plugins added: meta-bind, quickadd, tasks. Templates folder seeded; `wiki seed` extended to copy `templates/Templates/`.
- [x] T07 — P1 charts (was originally S03, merged forward). Five live `dataviewjs`-driven visualizations on the dashboard: source-type doughnut (`type:` distribution across knowledge/), top-15-tags bar, articles-per-folder bar, inbound-link histogram (graph-health buckets), daily-activity heatmap (last year, GitHub-style). Plugins added: obsidian-charts, heatmap-calendar. All five charts handle empty-vault and missing-plugin states gracefully.

## Verification

After all tasks:

```bash
# Engine-side
cd .wiki && uv run pytest tests/ -k dashboard_stats -q
uv run python scripts/dashboard-stats.py  # writes _dashboard-stats.md at vault root
test -f ../_dashboard-stats.md && grep -q "pending_compiles:" ../_dashboard-stats.md

# Vault-side (manual, in Obsidian)
# 1. Open vault. Confirm Dashboard.md opens automatically.
# 2. Confirm engine-status callout shows numeric values (not 'undefined').
# 3. Confirm all 5 dataview blocks render (no "Evaluation Error" boxes).
# 4. Run `wiki flush` from terminal; reload Obsidian Dashboard.md; confirm counts updated.
```

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `_dashboard-stats.md` filename: leading underscore so it sorts to bottom of file explorer and signals "machine-generated". Frontmatter-only, body empty. Mention in `templates/.gitignore` if it should be local-only — TBD during T03.
- If `lint.py --json` doesn't exist yet, T03 might surface a sub-task to add JSON output to lint. If it grows beyond a small change, defer to S02 (which is the lint-triage slice anyway).
- Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.
