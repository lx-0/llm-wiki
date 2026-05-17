# Axis-aware search tools (deferred)

**Deferred from**: office-hours backlinks-footer arc, 2026-05-17 (Q4 narrowest-wedge round).

## What was considered

Two CLI subcommands that would have ridden in the same bundle as `wiki backlinks`:

### `wiki search "<topic>" --type concept --domain X --author Y`

Frontmatter-aware ripgrep over `knowledge/`. Reads YAML frontmatter from each candidate file, filters by axes, returns matches with metadata.

- **Acute pain today?** No. Probe-run Query A (calendar/meeting concepts) was *trivial* with plain `grep` on `knowledge/index.md`. The axes (type/domain/author) are there in frontmatter but no current query has been blocked by their absence.
- **Future trigger to revisit**: vault crosses ~3k articles AND a recurring need to filter by domain/author is observed in dream-cycle or curiosity-loop traces.

### `wiki recent --since 14d --type fact`

mtime + axis filter, returns recently-modified articles.

- **Acute pain today?** No. Probe-run Query C was solvable with `find -mtime -14` + manual `stat` loop. Friction, but no blockage.
- **Future trigger to revisit**: when the dream-cycle or weekly-synthesis loop needs "what changed in the last week" as a primitive operation and is doing the `find` dance itself.

## Why rejected for this milestone

Pre-emptive tooling. The only structurally impossible query in the probe-run was **backlinks**. Topic-search worked trivially; temporal-search had friction but was unblocked. Building three commands when only one fills a real gap is over-building, and the Doug-Turnbull principle says: constraints force the agent to budget creativity — don't add tools before pain proves them.

## Architectural note

If/when these get built, they should **not** ride on the compile-time-footer mechanism of the backlinks milestone. The axes (`type`, `domain`, `author`, `compile-role`, `takes`) live in frontmatter — a query-time CLI that reads frontmatter from candidate files is the cleaner pattern. Different write-contract from backlinks (which materializes derived data); same Read-tier from the agent's view.

## Open questions for the day this gets picked up

- Should `wiki search` precompute a frontmatter index (`knowledge/.frontmatter.jsonl`) at compile time, or read frontmatter live per query? (Trade: stale-cache risk vs query latency at 5k+ articles.)
- Should the axes be hard-coded in the CLI flags or driven by a `config.yaml` whitelist (so adding a new frontmatter axis doesn't require code change)?
- Does `wiki recent` overlap with the existing `wiki status` health-dashboard's "recent activity" panel? Maybe `wiki recent` is just an exposed-as-CLI subset of what `health.py` already computes.

## Cross-refs

- `OFFICE-HOURS-backlinks-footer.md` — the parent pitch that this got carved out of.
- Memory: `feedback_no_reflex_tests_for_trivial_changes` (don't over-test) and `feedback_audit_premise_before_designing` (re-derive load-bearing metrics two ways) — both relevant when this returns.
