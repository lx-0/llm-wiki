---
milestone: M003
project: llm-wiki
size: L
created: 2026-05-02T16:58:33Z
status: planned
total_slices: 7
completed_slices: 1
---

# M003 Roadmap

**Goal:** Make the vault useful to the human reader, not just the agent: ship a rich Obsidian Homepage Dashboard that surfaces compile-pipeline state, lint-triage queues, and graphical reports (P1 single-snapshot + P2 time-series), plus a manually-curated MOC layer and a filterable Bases knowledge browser.

**Exit criteria:**

1. `Dashboard.md` opens automatically when the vault is opened (homepage plugin).
2. Engine-status callout shows live counts: pending compiles, failed flushes, lint warnings, total cost.
3. Four lint-triage queues clickable on Dashboard (orphan / stale / missing backlinks / failed flushes).
4. Five P1 charts render (source-type pie, tag-frequency, inlink histogram, articles/folder, daily-activity heatmap).
5. ≥3 MOCs in `knowledge/MOCs/` linked from Dashboard.
6. `state.history.jsonl` is appended by compile.py + flush.py.
7. Three P2 charts render (cumulative articles, cumulative cost, compile throughput).
8. Bases view as filterable knowledge browser.
9. `docs/PROCESS.md` documents the new layer.

## Slices

Slice detail lives in per-slice `M003-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 — Dashboard scaffold + homepage plugin (basic Dashboard.md, engine-status callout with counts only, recents/top-concepts dataview tables, install homepage) — see `M003-S01-PLAN.md`
- [ ] S02 — Lint-triage queues (surface lint.py warnings as collapsible callouts on Dashboard: orphans / stale / missing backlinks / failed flushes)
- [ ] S03 — Reserved (originally "P1 charts + chart plugins"; the 5 P1 charts and both plugins were absorbed into S01-T07. Remaining S03 candidates: Mermaid timelines / Gantt for milestone visualisation, Datacore card views once stable, click-through chart drilldowns. Re-scope at slice-time.)
- [ ] S04 — MOC layer (knowledge/MOCs/ directory, AGENTS.md schema for `type: moc`, seed 2-3 hand-written MOCs, Dashboard MOC section)
- [ ] S05 — state.history.jsonl + P2 charts (append-only history layer in utils.py, wire compile.py + flush.py, install obsidian-tracker, add 3 time-series charts)
- [ ] S06 — Bases knowledge browser (native filterable card/table view of knowledge/ with type/tag/status facets)
- [ ] S07 — Dashboard cache robustness (stop `wiki seed --force` from clobbering `_dashboard-*.md`; surface silent refresh failures from `flush.py` + `wiki` shell wrapper) — see `M003-S07-PLAN.md`

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

S01 → S02 → S03 → S04 → S05 → S06 → S07. (S07 was inserted post-S01 after a real lxw bug — could be pulled forward in front of S04-S06 if dashboard reliability matters more than new dashboard surface area.)

Inter-slice dependencies:
- S02 depends on S01 (Dashboard exists to add callouts to).
- S03 depends on S01 (Dashboard exists to add charts to).
- S04 has no hard dependency on S02/S03 but logically follows (Dashboard has a MOCs section to populate).
- S05 depends on S01 (Dashboard exists to add Reports section to). Engine-side change touches `compile.py` + `flush.py` — verify no regression on the Mailbox flush path from M002.
- S06 depends on S01 + S04 (Bases facets include MOC-vs-concept-vs-connection).

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update STATE.md + ROADMAP.md
