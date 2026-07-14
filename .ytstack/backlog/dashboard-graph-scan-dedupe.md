# Dashboard refresh — share the corpus link-graph scan (real fix for the 120s timeouts)

Status: **backlog** (2026-07-14 triage, finding #6). The 300s cap bump
(shipped) raises the ceiling; this is the structural fix.

## Problem
`dashboard_stats.py::compute_stats()` calls `count_lint_warnings()` which runs
6 lint checks inline; `check_broken_links` + `check_orphan_pages` +
`check_missing_backlinks` each independently walk all ~1947 knowledge articles
and resolve every wikilink (`core/links.py`). `dashboard_lint.py` then recomputes
the SAME 3 corpus scans in a second subprocess. On every flush, under iCloud
fs-stat latency variance, this occasionally crosses the 120s cap (29 timeouts
all-time, 5 in the last 14d; 641 successful refreshes, median 20.1s).

## Fix
Compute the corpus link-graph ONCE per flush and share it across
`dashboard_stats` + `dashboard_lint` (they currently each rebuild the same 3
scans in separate subprocesses). Options: a cached graph artifact under
`.wiki/state/` keyed by a corpus mtime-hash, or a single combined refresh script
that both surfaces read. Effort M, risk medium (touches the dashboard refresh
path both scripts depend on).

Files: `scripts/dashboard/dashboard_stats.py`, `scripts/dashboard/dashboard_lint.py`,
`scripts/lint.py`, `scripts/core/links.py`, `scripts/flush.py`.
