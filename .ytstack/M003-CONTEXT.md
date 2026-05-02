---
milestone: M003
project: llm-wiki
created: 2026-05-02T16:58:33Z
size: L
---

# M003 — Context

## Goal

Make the vault useful to the human reader, not just the agent: ship a rich Obsidian Homepage Dashboard that surfaces compile-pipeline state, lint-triage queues, and graphical reports (P1 single-snapshot + P2 time-series), plus a manually-curated MOC layer and a filterable Bases knowledge browser.

## Exit criteria

1. `Dashboard.md` opens automatically when the vault is opened (via `homepage` plugin in `templates/.obsidian/community-plugins.json` + workspace config).
2. Engine-status callout on Dashboard shows live counts: pending compiles, failed flushes, lint warnings, total LLM cost (lifetime + today).
3. Four lint-triage queues are visible and clickable on the Dashboard: orphan articles, stale articles, missing backlinks, failed flushes.
4. Five P1 charts render (single-snapshot, no history needed):
   - source-type pie (`type:` frontmatter aggregated)
   - tag-frequency bar (top 20 tags)
   - inbound-link histogram (articles bucketed by inlink count)
   - articles-per-folder bar
   - daily-activity heatmap calendar (last 90 days)
5. At least three MOCs exist under `knowledge/MOCs/`, with `type: moc` frontmatter, and are linked from Dashboard.
6. `state.history.jsonl` is appended by `compile.py` (per file compiled) and `flush.py` (per flush event), with schema `{ts, event, source, articles_changed, tokens, cost, lint_warnings, total_articles}`.
7. Three P2 time-series charts render from history: cumulative articles over time, cumulative LLM spend over time, compile throughput (per day).
8. Bases view as a filterable knowledge browser (`type` / `tag` / `status` facets) is embedded in or linked from Dashboard.
9. `docs/PROCESS.md` documents the new three-layer split (Dashboard / index / MOCs) and the history layer.

## Size

L — see `M003-ROADMAP.md` for slice breakdown. Six slices: S01 Dashboard scaffold, S02 Lint-triage queues, S03 P1 charts + plugins, S04 MOC layer, S05 history layer + P2 charts, S06 Bases browser.

## Decisions locked in discuss phase

- 2026-05-02: Full vault-UX scope including state-history layer, Bases browser, and manual MOCs. User explicitly chose the broadest option ("alles"); narrower variants rejected.
- 2026-05-02: MOCs in v1 are **manually curated** (no LLM suggestion stage). LLM-suggested MOCs are deferred to a later milestone (sketched as S07 in `backlog/vault-dashboard.md`).
- 2026-05-02: Charts split into P1 (single-snapshot, free, no history dependency) and P2 (requires `state.history.jsonl`). P2 charts ship in S05 after history layer lands.
- 2026-05-02: `knowledge/index.md` stays unchanged — agent-facing flat compile-target. Human navigation lives in `Dashboard.md` + `MOCs/`.
- 2026-05-02: No backfill of `state.history.jsonl`. History starts the day S05 lands; cumulative numbers anchor on point-in-time `state.json`.
- 2026-05-02: `Dashboard.md` filename is plain ASCII (no emoji prefix), per shell-path safety. Per-install override remains possible.

## Open questions

- Does the `homepage` plugin reliably auto-open `Dashboard.md` on iOS Obsidian? (Worth confirming in S01 verification; fallback is to set `Dashboard.md` as the default new-tab note.)
- Bases (1.9.10+) requires a minimum Obsidian version. Confirm vault install instructions in `install.sh` document the version bump.
- Should compile.py emit a `needs_review: true` frontmatter flag when LLM confidence is low? Sketched in backlog as a Pending-Review-queue source. Defer to S02 — only needed if we want a 5th triage queue.
- `obsidian-charts` vs Mermaid `xychart-beta` for the P1 charts: pick once during S03. `obsidian-charts` is the safer default (richer Chart.js features).

## References

- Backlog source: `backlog/vault-dashboard.md` — full design synthesis with section-by-section dashboard layout, plugin matrix, and per-slice scope.
- Related backlog: `backlog/connection-quality.md` — MOCs are also one of the 5 fixes there; this milestone delivers the MOC anchor without the LLM-suggestion stage.
- lx vault reference dashboard: `/Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/lx/🗺️ Dashboard.md`.
