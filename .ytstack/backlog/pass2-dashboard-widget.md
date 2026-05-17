# Pass-2 cross-study finding on the Obsidian dashboard

DECISIONS.md M019 closeout (2026-05-17) flagged this as deferred:
*"Operator dashboard widget surfacing the latest Pass-2 output in
Obsidian — current pattern is 'operator opens
`reports/analyses/<latest>.md` directly'."*

The pattern works but is friction. Pass-2 is the consumption surface
of the whole reports/ arc; if it's behind a click-tree-folder-find
flow, it loses against the dashboard's other panes (Personal Tasks,
Stats, History).

## What's missing

A dashboard pane (rendered in `templates/dashboard.md`) that shows:

- The latest `<vault>/reports/analyses/<UTC-ts>.md`'s headline finding
  (first H2 + first paragraph) — ≤ ~200 words.
- A datestamp ("Pass-2 cross-study synthesis · 2026-05-24") so the
  operator sees stale-by-N-days at a glance.
- A "↗ open" wikilink to the full analysis file.
- (Optional) the same pattern for the **latest Pass-1 per-study
  `_analysis.md`** if the operator is mid-week and Pass-2 hasn't fired
  yet — keeps the dashboard useful between Pass-2 cycles.

## Tooling shape

Same pattern as the existing `_dashboard-stats.md` /
`_dashboard-lint.md` cache files:

- `scripts/dashboard/dashboard_reports.py` writes
  `_dashboard-reports.md` into the vault.
- Triggered on the same hooks (`flush.py:refresh_dashboard_*`,
  shell-wrapper helpers in `wiki compile / study run / analyze /
  seed`).
- Marker-region in `dashboard.md` plus the cache-file include —
  matches the M003 dashboard contract.

## Size

S — half-day. Reads existing files, renders markdown, writes one
cache file. No SDK calls. No schema work.

## Ripens when

- Operator has done ≥1 Pass-2 cycle (so the "latest" pointer is
  non-trivial). Pass-2 runs weekly via `study_run_due` piggyback + `wiki
  analyze`, so this ripens within a week of the 2026-05-24 week-1
  review.

## Status

**BACKLOGGED** — 2026-05-17. Wait until at least one Pass-2 has fired
in the vault so the pane has something to render against. The week-1
review (2026-05-24) is the natural trigger point.
