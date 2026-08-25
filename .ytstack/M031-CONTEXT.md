---
milestone: M031
project: llm-wiki
created: 2026-08-25T15:30:00Z
size: L
---

# M031 -- Context (Reliability Wave)

## Goal

The pipeline defects found by the 2026-08-25 full-state audit are fixed at the class level and the vault runs clean again: flush-extract works and its 234-deep retry queue drains to zero, knowledge/index.md matches the corpus (writer fixed + rebuilt), the bash-`[[…]]` wikilink false-positive class is dead across lint/links/publish, the small-fix package lands, and doctor gains the freshness checks that would have caught all three cluster outages within days.

## Exit criteria

1. Flush: root cause of the cli_crash class NAMED with evidence (not pattern-matched — three historic causes share this surface); fix + 70 KB E2E regression fixture; live: a real session flushes end-to-end on lxw and `daily/<d>/sessions.md` is written again.
2. Retry queue: drain decoupled from compile cadence (catch-up mode); live: `sessions/failed-flushes/` from 234 → 0 (or explicitly tombstoned), inflow ≤ outflow by construction.
3. Index: writer upserts (no duplicate rows possible, test-pinned); one-shot rebuild reconciles lxw (rows == corpus count, 0 duplicates, 0 junk targets); lint gains a drift gate.
4. Link grammar: bash-test shapes are not wikilinks (fixtures for all observed shapes; Obsidian behavior live-verified first); lint/links counts drop by the measured class size; publish re-sends previously-degraded articles automatically via content hash.
5. S-fix package: lint 'Concept domain tag' crash, piggyback_runner stale last_error, the 9 missing migration keys, legacy dollar-counter retired, gmeet Drive-404 dead-letter, scan_youtube dead config.
6. Doctor: substrate-freshness check (newest artifact age per configured collector vs cooldown) + piggyback-health check (failed:* / last_run > 3× cooldown) — both deterministic, both would have flagged the June/August outages.
7. Suite green; knobs + migrations same commit; docs/CHANGELOG/infographics in the same arc.

## Size

L -- 4 slices, see M031-ROADMAP.md.

## Decisions locked in discuss phase

- 2026-08-25: Scope = audit lane A (reliability) + the structural never-again piece (doctor checks). Lane B (kcma-d8 host, mobile-bridge/LaunchAgents) is operator infra — diagnosis on request, not in this milestone. Triage-65/Suggestions-10 remain operator content decisions.
- 2026-08-25: Quick-wins C executed ahead of the milestone: features.health_trends + concept_reconciliation enabled (+ piggyback blocks), `links --fix --yes` (19 corrections/26 links/20 files), Fleet/Township `correct apply` sweep launched.
- Source backlog files: flush-extract-outage.md, index-md-drift.md, bash-brackets-wikilink-class.md, gmeet-export-dead-letter.md.

## Open questions

- E3 (`models.compile_model` dead knob): honest fix is either wiring route.py to CONFIG or removing/renaming the knob — DESIGN decision (Haiku hardcode was a deliberate cost optimization). Decide during S03, one question to operator if both options feel wrong.
- Retry-drain shape: own piggyback with queue-proportional limit vs. drain-on-flush-success — decide in S01 from the root cause.
