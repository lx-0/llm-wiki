---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T22:40:00Z
current_milestone: M003
active_slice: S06
active_task: T02
---

# State

**Status:** M002 **done** (2026-05-02; 25 pytest tests green; commits `15b4916` S01, `14bf844` S02, `4e52520` S03, `b884bf1` finalize). Reader/Filter adapter seam landed for Thunderbird-mbox, All-Inkl-Procmail, and Gmail-API; legacy `scripts/scan-email.py` + `scripts/thunderbird-rules.py` deleted; `wiki_config.py` enforces nested `reader:`/`filter:` schema; round-robin config backup wired into every `wiki config set`. **Live Gmail smoke deferred** as operator-side action (drop `client_secret.json` → `wiki gmail-auth <id>` → `wiki collect email --account <id>`) — does not block M003.

**Doc restructure (2026-05-02 PM, commits `22900dc` + `59a5175`):** README went 460 → 311 lines via 9-repo audit (basic-memory, mem0, ollama, simonw/llm, nanoGPT, OpenHands, fabric, claude-memory-compiler, karpathy/nanoGPT) plus consistency pass against `.ytstack/`. Auxiliary docs created: `docs/cli.md` (CLI reference), `docs/engine-layout.md` (engine internals), `docs/vault-tour.png` (Obsidian-mockup infographic via lo-fi-wireframing-kit). All linked docs got TOCs. Two backfill DECISIONS.md entries: naming vocabulary lock + `.venv/` location hard-rule. README "8 collectors" claim corrected to "9 substrate sources" (only `scan-email` is on the formal Collector pattern post-M002). Deferred follow-ups in `backlog/readme-polish.md`.

**Status:** M003 in progress (1/6 slices done — S01 grew from 5 → 8 tasks during execution). S01 closed with rich interactive Dashboard: capture buttons (Meta Bind + QuickAdd), live engine-status callout with pending-list, 5 graphical charts (Source-type doughnut, Top-15 tags bar, Article freshness, Inbound-link histogram, Daily activity heatmap), Inbox/Pending-review/Tasks triage, Run-buttons (compile / lint / refresh-stats via Shell commands plugin), Orphan list. Theme-aware Chart.js colors via Obsidian CSS vars, responsive grid via cssclasses + CSS snippet.

**Wiki CLI massive expansion** — gained `compile / flush / lint / query / review-wiki / seed / correct` subcommands; was lifecycle-only before. `_run_script` + `_refresh_dashboard_stats` helpers dedupe wrappers.

**Hard-facts subsystem (user-led, parallel to S01)** — new `knowledge/facts/<slug>.md` with `type: fact` frontmatter. `wiki correct add/list/remove/edit/path` CLI in `scripts/correct.py`. `prompts/compile_main.md` injects facts as authoritative override over source material. Lint check_article_type knows about `facts/ → fact`. Migration script + tests adjusted accordingly.

**Root-cause fixes that landed:**
- `compile_main.md` now sets `type:` per folder; `AGENTS.example.md` documents knowledge/ frontmatter schema; lint flags missing_type / type_mismatch (auto-fixable); `scripts/migrate_add_type.py` backfills legacy articles. Replaces earlier symptom-fix where dashboard chart fell back to folder name.
- `lint.py:check_stale_articles` defensive isinstance handling for `state.ingested[rel]` (string in current schema, dict in legacy). Per-check try/except in main loop so one crash doesn't kill the run.
- `templates/.obsidian/plugins/dataview/data.json` seeds `enableDataviewJs: true` so charts render without manual toggle.
- Meta Bind buttons: `cssclasses: [wiki-dashboard]` instead of inline `<div>` wrappers — Meta Bind post-processor doesn't run inside raw-HTML context.

**`wiki seed` command** — additive in-place re-application of templates to installed vaults (community-plugins.json merged via jq, never destructive). `wiki seed --force` overwrites existing files. `lib/seed.sh` is the shared logic, used by both `install.sh` and the CLI.

**Plugins shipped** (8 community + Obsidian-builtin): dataview, homepage, obsidian-charts, heatmap-calendar, obsidian-meta-bind-plugin, obsidian-tasks-plugin, obsidian-shellcommands, quickadd, plus existing obsidian-excalidraw-plugin. Plus CSS snippet `wiki-dashboard.css`.

**Tests:** 37 pytest tests green (was 25 pre-M003).

**M003 — Human Vault UX:** Dashboard.md (auto-opens via homepage plugin) with engine-status callout, lint-triage queues, P1+P2 charts (5+3, single-snapshot + time-series), MOC layer (≥3 manually curated), state.history.jsonl append-only history, Bases knowledge browser. Six slices S01–S06. Source design in `backlog/vault-dashboard.md`; locked decisions + exit criteria in `M003-CONTEXT.md`.

Carried-forward candidates from M002 (deferred to M004+): Collector-rollout to other substrates, multi-vault ingest, source-onboarding cadence.

**M004 done (2026-05-02):** Agent-Task framework shipped. `scripts/agent_spec.py` (parser, 8 validation cases), `scripts/agent_task.py` (SDK runner with `--list / --dry-run / --var`), `scripts/agent_buttons.py` (discovery + dashboard region-rewrite), `wiki agent <id>` CLI. First concrete task: `prompts/agent_summarize-day.md` (Haiku, Read/Edit/Write, primary button). Auto-wiring via `wiki seed`: jq-merge into shell-commands data.json + marker-based region replace in dashboard.md. 20 pytest tests green (17 spec + 3 summarize-day smoke). PROCESS.md §14 + KNOWLEDGE.md learning + DECISIONS.md two entries (framework + region-marker pattern). Live vault patched, button visible in Run row after reload.

## Next action

M004 closed. Two paths:
- **Reassess roadmap** — does the catalogue need more agent tasks now (review-mocs, weekly-digest, extract-todos)? Or move to a different milestone.
- **Carry-forward**: Auto-pruning of removed agent buttons (currently additive only), `--prune-agent-buttons` flag, per-task scheduling/piggyback integration. All deferred to backlog.

## Open decisions

- **Multi-vault ingest** — see Next action above. Carried forward to M003 scoping.
- **Source-onboarding cadence** — see Next action above. Carried forward.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
