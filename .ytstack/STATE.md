---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T10:20:23Z
current_milestone: none
active_slice: none
active_task: none
---

# State

**Status:** initialized 2026-05-02 from validated pitch (`OFFICE-HOURS-self-cartography-engine.md`). Brownfield-doc-migration completed same day (`docs/design-decisions.md` content moved into `.ytstack/KNOWLEDGE.md` "Hard-won learnings"; `docs/plans/*` moved into `.ytstack/backlog/*`; CLAUDE.md / AGENTS.md / docs/concept.md / docs/PROCESS.md / hooks / scripts pointers updated; `project_followups.md` claude-memory moved to `.ytstack/backlog/cleanup-followups.md`). No milestone planned yet.

## Next action

Run `ytstack:plan-milestone` to define M001. **The milestone scope has not been chosen** — the operator needs to pick what M001 is actually about. Candidate framings to consider during plan-milestone:

- Active-use loop (close Q5 build-vs-use weak spot — agents read from `knowledge/` automatically, dashboard surfaces wiki in daily flow)
- A real feature from `.ytstack/backlog/` (collectors, nas-ingest, obsidian-plugin, compiler-suggestions, wiki-config, karpathy-comparison)
- Something else the operator decides

Whatever the choice, the cleanup follow-ups in `.ytstack/backlog/cleanup-followups.md` (AGENTS.example.md template, dashboard.md template, .obsidian/ seeds, SKIP_PREFIXES → CONFIG, lib/config.sh generalization, vault hygiene) are not currently scoped to a milestone — they remain in the backlog until promoted.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
