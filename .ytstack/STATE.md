---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-02T18:00:00Z
current_milestone: none
active_slice: none
active_task: none
---

# State

**Status:** M002 **done** (2026-05-02; 25 pytest tests green; commits `15b4916` S01, `14bf844` S02, `4e52520` S03, `b884bf1` finalize). Reader/Filter adapter seam landed for Thunderbird-mbox, All-Inkl-Procmail, and Gmail-API; legacy `scripts/scan-email.py` + `scripts/thunderbird-rules.py` deleted; `wiki_config.py` enforces nested `reader:`/`filter:` schema; round-robin config backup wired into every `wiki config set`. **Live Gmail smoke deferred** as operator-side action (drop `client_secret.json` → `wiki gmail-auth <id>` → `wiki collect email --account <id>`) — does not block M003.

## Next action

Pick the next milestone. Two open candidates from M002 close-out (and the original pitch):

- **Roll the Collector pattern out to other substrates** (calendar, browser, screenshots, tabs). Mailbox proved the seam; M003 would replicate it across the rest. Likely M-sized.
- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être. Probably needs an `office-hours` round before scoping.
- **Source-onboarding cadence** — onboard dormant vaults / exports / past-system files manually now, or wait for collectors? Trade-off: incomplete map vs. noisy ingest.

Run `ytstack:plan-milestone` (or `ytstack:office-hours` first if the pitch needs sharpening) to lock M003.

## Open decisions

- **Multi-vault ingest** — see Next action above. Carried forward to M003 scoping.
- **Source-onboarding cadence** — see Next action above. Carried forward.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
