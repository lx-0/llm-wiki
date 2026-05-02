---
milestone: M003
slice: S02
project: llm-wiki
created: 2026-05-02T18:30:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M003-S02 — Slice Plan

**Goal:** Four collapsible lint-triage callouts on `Dashboard.md` (orphans / stale / missing-backlinks / failed-flushes), live from a `_dashboard-lint.md` cache file refreshed as a flush-piggyback. Operator can scan the queues at a glance and click through to the offending file.

**Out of scope (deferred):** charts (S03), MOCs (S04), history-driven time-series (S05), Bases browser (S06). No changes to `lint.py` itself — its check functions are imported, not re-implemented.

## Architectural decisions baked in

- **Separate cache file.** `_dashboard-lint.md` lives at vault root next to `_dashboard-stats.md`. Counts-only vs. counts+detail justifies the split; allows independent re-render cadence later.
- **Import, don't shell out.** `scripts/dashboard_lint.py` imports `check_orphan_pages`, `check_stale_articles`, `check_missing_backlinks` directly from `scripts/lint.py`. No `--json` flag on lint.py needed; no subprocess overhead. Same pattern S01-T03 used for `dashboard_stats.py`.
- **Failed-flushes path.** Authoritative location is `scripts/sessions/failed-flushes/` (engine-side). The cache enumerates files there and renders one entry per failed flush.
- **Obsidian Callouts, not Dataview tables.** Each queue is a `> [!warning]- Title (N)` collapsible callout with an `![[_dashboard-lint#<section>]]` embed inside. Empty queues render `> [!success] Title (0)` with no body, so they auto-collapse visually. No Dataview JS needed → faster, fewer plugin deps.
- **No new plugins.** Callouts are core Obsidian; embeds are core; everything else (Meta Bind, Dataview, Tasks, Charts) already seeded by S01.

## Tasks

- [ ] T01 — Implement `scripts/dashboard_lint.py`. Imports `check_orphan_pages`, `check_stale_articles`, `check_missing_backlinks` from `scripts.lint`. Enumerates `scripts/sessions/failed-flushes/*.md` (or whatever extension is used there — verify at impl-time) for the fourth queue. Writes `_dashboard-lint.md` at vault root with: (a) frontmatter `orphans_count`, `stale_count`, `missing_backlinks_count`, `failed_flushes_count`, `last_updated_ts`; (b) four `## <queue>` Markdown sections, each one line per issue: `[[<wikilink>]] — <short detail from check.detail>`. Hook into `flush.py` post-`maybe_trigger_compile` next to the existing `dashboard_stats.py` call. Done when `wiki flush` produces a fresh `_dashboard-lint.md` with non-zero counts on a vault that has known orphans/stale/etc.

- [ ] T02 — Update `templates/Dashboard.md`. In the existing engine-status section, replace the single "lint warnings" inline-field number with a new "## 🛡 Lint triage" section containing four collapsible callouts: orphans, stale, missing-backlinks, failed-flushes. Use `> [!warning]- Orphans (N)` syntax with `![[_dashboard-lint#Orphans]]` embed inside; flip to `> [!success] Orphans (0)` (no embed) when count == 0. Counts pulled from `_dashboard-lint.md` frontmatter via Dataview inline-field reference. Update `templates/wiki-dashboard.css` if callout styling needs scoping. Done when Dashboard.md renders all four callouts in Obsidian, expandable and collapsible, with empty queues showing the success variant.

- [ ] T03 — Wire `wiki lint` and `wiki seed` to refresh the cache. `wiki lint` already auto-refreshes `_dashboard-stats.md` post-run (S01-T08 pattern); extend the same hook to also call `dashboard_lint.py`. `wiki seed` should regenerate `_dashboard-lint.md` after seeding so a fresh-install vault doesn't show a stale or empty cache. Done when (a) `wiki lint` updates both stats + lint cache files, and (b) running `wiki seed` on a fresh vault produces a populated `_dashboard-lint.md`.

- [ ] T04 — Update `docs/PROCESS.md`. In the "Three-layer vault UX" section seeded in S01-T05, add a paragraph documenting the lint-triage layer: how `_dashboard-lint.md` is produced, when it's refreshed, what each of the four queues represents. Add `dashboard_lint.py` to the piggyback-script list. Cross-link from `templates/Dashboard.md` header comment if the operator-facing explanation belongs there too. Done when `grep -n "dashboard_lint" docs/PROCESS.md` returns the new section.

- [ ] T05 — Verification fixtures + manual smoke. Add a pytest fixture under `tests/` that builds a temp vault with: 1 orphan article, 1 stale article (mtime > stale-threshold), 1 article with broken backlinks, 1 placeholder failed-flush file. Run `dashboard_lint.py` against the fixture; assert each frontmatter count == 1 and each section contains exactly one wikilink. Manual smoke on the live `lxw` vault: open Obsidian, confirm 4 callouts render without Dataview errors, click through one wikilink, confirm it lands on the right file. Done when `uv run pytest tests/ -k dashboard_lint -q` passes and the manual smoke note is added to `M003-S02-PLAN.md` Notes section.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. Exit criterion #3 of M003 ("Four lint-triage queues clickable on Dashboard") satisfied.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)

## Notes (T05 manual smoke, 2026-05-02)

`dashboard_lint.py --dry-run` against the lxw vault (`/Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw/`) produced:
- orphans=0 (knowledge linkage healthy — index covers everything)
- stale=25 (daily/2026-04-13.md … 2026-05-02.md — sources changed since last compile)
- missing_backlinks=1838 (high but consistent with `wiki lint --structural-only` output)
- failed_flushes=1 (one stub from a prior crashed flush)
- last_updated_ts populated, frontmatter parsed cleanly

Live Obsidian smoke deferred until `wiki update` lands the engine commits in the vault — engine repo is at `commit 541ab76` (T04), vault `.wiki/` still on `c22a125` (M004). Once pushed and updated, operator should see four callouts: Orphans `[!success] (0)`, the other three `[!warning]-` collapsed.
