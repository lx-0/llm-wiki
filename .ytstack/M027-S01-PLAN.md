---
milestone: M027
slice: S01
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 5
completed_tasks: 0
---

# M027-S01 -- Slice Plan

**Goal:** Lock the three irreversible gates (filename-PII rule, derived-facts
sensitivity policy, answer-landing contract) and land the `watched_folders`
config surface -- so nothing downstream can ship a broad PII surface before the
policies exist.

## Tasks

- [ ] T01 -- Decide + document the filename/path-PII sanitization rule (what masks/strips sensitive filenames before any index hits `raw/index/` or a prompt); record in DECISIONS.md + a policy doc under `prompts/` or `docs/`.
- [ ] T02 -- Decide + document the derived-facts sensitivity policy (what distilled facts may persist vs. stay out; `sensitivity:` frontmatter as health); record in DECISIONS.md.
- [ ] T03 -- Decide + document the answer-landing contract (resolve a/b/c: curiosity-answer artifact vs. direct knowledge-write vs. daily rollup); record in DECISIONS.md with the reasoning on why the chosen path doesn't fight compile-distill / agent-scope contracts.
- [ ] T04 -- Implement the filename/path sanitization primitive (pure function + unit tests) that the index build will call before writing.
- [ ] T05 -- Add `personal.watched_folders` config schema (`config.py` + `config.example.yaml` + `migrations/migrate_config_keys.py`, same commit per the config-knob rule); validation only, no scanning yet.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. The three gate
decisions are written in DECISIONS.md and the sanitization primitive is tested.

## Notes

These are the milestone's blocking gates (M027-CONTEXT Q1-Q3). T01-T03 are
decisions first; a wrong call on T01/T02 leaks PII irreversibly, a wrong call on
T03 means the backend can't be built. Do not start S02 (index writes) before
T01+T04 land.
