---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T14:47:46Z
current_milestone: M002
active_slice: none
active_task: none
---

# State

**Status:** M002 planned (size M, 3 slices). Ready to slice. M001 done 2026-05-02.

**M002 — Mailbox-Adapter seam + Collector backbone.** Goal: email scanning + filter-application work for Gmail accounts (in addition to Thunderbird-mbox + All-Inkl-Procmail) via a Reader/Filter adapter seam, so new backends don't touch scan/execute call-sites. Architecture locked through the `improve-codebase-architecture` skill flow; full design in `M002-CONTEXT.md`, slice breakdown in `M002-ROADMAP.md`. Domain glossary added at repo root: `CONTEXT.md`.

## Next action

Run `ytstack:slice-milestone` to lock the per-slice plans + verification steps. Tentative breakdown:

- **S01** Backbone + first proof (domain types, Protocols, Registry, EmailCollector with FakeReader, `wiki collect` CLI)
- **S02** Migrate existing capability (Thunderbird + AllInkl adapters; delete old scan-email.py + thunderbird-rules.py; CONFIG schema enforced)
- **S03** Add Gmail (Reader + Filter via Gmail API; OAuth cache; live smoke test)

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
