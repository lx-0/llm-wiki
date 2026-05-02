---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T17:58:23Z
current_milestone: M003
active_slice: none
active_task: none
---

# State

**Status:** M002 **done** (2026-05-02; 25 pytest tests green; commits `15b4916` S01, `14bf844` S02, `4e52520` S03, `b884bf1` finalize). Reader/Filter adapter seam landed for Thunderbird-mbox, All-Inkl-Procmail, and Gmail-API; legacy `scripts/scan-email.py` + `scripts/thunderbird-rules.py` deleted; `wiki_config.py` enforces nested `reader:`/`filter:` schema; round-robin config backup wired into every `wiki config set`. **Live Gmail smoke deferred** as operator-side action (drop `client_secret.json` → `wiki gmail-auth <id>` → `wiki collect email --account <id>`) — does not block M003.

**Doc restructure (2026-05-02 PM, commits `22900dc` + `59a5175`):** README went 460 → 311 lines via 9-repo audit (basic-memory, mem0, ollama, simonw/llm, nanoGPT, OpenHands, fabric, claude-memory-compiler, karpathy/nanoGPT) plus consistency pass against `.ytstack/`. Auxiliary docs created: `docs/cli.md` (CLI reference), `docs/engine-layout.md` (engine internals), `docs/vault-tour.png` (Obsidian-mockup infographic via lo-fi-wireframing-kit). All linked docs got TOCs. Two backfill DECISIONS.md entries: naming vocabulary lock + `.venv/` location hard-rule. README "8 collectors" claim corrected to "9 substrate sources" (only `scan-email` is on the formal Collector pattern post-M002). Deferred follow-ups in `backlog/readme-polish.md`.

**Status:** M003 in progress (1/6 slices done). S01 — Dashboard scaffold + homepage plugin landed. 5 tasks completed, 4 new pytest tests green, install.sh + dashboard.md template + scripts/dashboard_stats.py + flush.py post-flush refresh wired up. docs/PROCESS.md gained section 12 "Vault UX Layer".

**M003 — Human Vault UX:** Dashboard.md (auto-opens via homepage plugin) with engine-status callout, lint-triage queues, P1+P2 charts (5+3, single-snapshot + time-series), MOC layer (≥3 manually curated), state.history.jsonl append-only history, Bases knowledge browser. Six slices S01–S06. Source design in `backlog/vault-dashboard.md`; locked decisions + exit criteria in `M003-CONTEXT.md`.

Carried-forward candidates from M002 (deferred to M004+): Collector-rollout to other substrates, multi-vault ingest, source-onboarding cadence.

## Next action

S01 complete. Two paths:
- **Commit S01** before moving on (recommended — clean checkpoint).
- **Slice + execute S02** (Lint-triage queues — surface lint.py warnings as collapsible callouts on Dashboard).

Run `ytstack:reassess-roadmap` if S01 surfaced anything that should change S02–S06 scope. Otherwise next slice can be planned via `ytstack:slice-milestone` (or directly written like S01 was).

## Open decisions

- **Multi-vault ingest** — see Next action above. Carried forward to M003 scoping.
- **Source-onboarding cadence** — see Next action above. Carried forward.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
