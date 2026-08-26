---
milestone: M031
project: llm-wiki
size: L
created: 2026-08-25T15:30:00Z
status: planned
total_slices: 4
completed_slices: 0
---

# M031 Roadmap (Reliability Wave)

**Goal:** Audit-found defects fixed at class level: flush + retry queue, index drift, link grammar + S-fixes, doctor freshness gates.

**Exit criteria:** see M031-CONTEXT.md (7 items, all live-verified on lxw).

## Slices

- [ ] S01 -- Flush outage: systematic root-cause of the cli_crash class (evidence-first), fix + 70 KB regression, retry-drain decoupled with catch-up, live queue 234 → 0, sessions.md flowing
- [x] S02 -- Index drift DONE 2026-08-26: root cause was the LLM prompt step itself (told to upsert a table it must not read) — replaced by the deterministic `core/index_sync.py` post-compile pass + `wiki reindex` CLI; prompt step removed. Live: 362 deduped / 33 dropped / 574 appended, control dry-run 2024 rows · 0 changes · idempotent (== corpus). Drift gate folded into S04's doctor checks (one home). Expected one-time follow-on: ~574 publish updates (better descriptions) on the next piggyback fire.
- [ ] S03 -- Link grammar + S-fix package: bash-bracket guard in core/links.py (Obsidian-verified), lint-check crash, stale last_error, 9 migration keys, dollar-counter retirement, gmeet dead-letter, scan_youtube cleanup, compile_model-knob decision
- [ ] S04 -- Never-again + closeout: doctor substrate-freshness + piggyback-health checks, docs/CHANGELOG/infographics, milestone reassess

## Run order

Sequential; `ytstack:reassess-roadmap` at each slice boundary.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all summarize-confirmed; update `completed_slices`; on completion flip `status`.
