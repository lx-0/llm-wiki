---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T11:30:00Z
current_milestone: M001
active_slice: none
active_task: none
---

# State

**Status:** M001 planned (size M, 3 slices). Ready to slice.

**M001 — Engine-Cleanup.** Goal: a new install of llm-wiki produces a working, opinionated vault out of the box, with engine artefacts cleanly separated from user content. Bundles 5 backlog items: cleanup-followups, engine-layout-cleanup, install-symlink-skills, clippings-sweep, wiki-config. Full context in `M001-CONTEXT.md`; tentative slicing in `M001-ROADMAP.md`.

## Next action

Run `ytstack:slice-milestone` to break M001 into concrete slices + tasks. Tentative slice breakdown:

- **S01** install-seeds + skill-symlinks (cleanup-followups template seeds + install-symlink-skills)
- **S02** layout refactor + Clippings sweep (engine-layout-cleanup + clippings-sweep)
- **S03** audit + minor cleanups (cleanup-followups remaining items + wiki-config)

Slicing locks the per-slice file paths and verification steps.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
