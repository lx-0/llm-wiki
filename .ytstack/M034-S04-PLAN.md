---
milestone: M034
slice: S04
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 4
completed_tasks: 0
---

# M034-S04 -- Slice Plan

**Goal:** `wiki seed` runs in Python, with every template merge at parity on the fixture vault
and on a copy of the live `.obsidian/`; `lib/seed.sh` (708 lines) is deleted.

## Tasks

- [ ] T01 -- The seed core:
  - the template walk and its skip rules;
  - semantic file equivalence (what `jq -S` gave, in `json`);
  - the custom overlay: compute, apply, extract into `.wiki/custom/`.

  Open question 4 is decided in DECISIONS. Unit tests run on fixture templates.
- [ ] T02 -- The special merges:
  - community plugins, `appearance.json`, the `.env` example;
  - meta-bind data, agent shell commands, the dashboard agent buttons.

  Each at parity with the bash on the fixture and on a copy of the live vault's `.obsidian/`
  (the real data shape — arrays included; read-only source, copied to a tmp dir).
- [ ] T03 -- The `seed` command (`--force`, `--check`, `seed extract-custom`). The `--check`
  drift report uses the engine-relevant subset if the port makes that cheap
  (`backlog/seed-semantic-diff.md`). `test_seed_preserves_caches.py` is kept green.
- [ ] T04 -- `lib/seed.sh` is deleted along with its `wiki` call sites. The oracle passes, the
  docs are updated, and a scratch `wiki seed` and `wiki seed --force` match the bash goldens.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; no bash left for seeding.

## Notes

The memory "round-trip on the real data shape before a live `--force`" applies: the live
vault's `.obsidian/` JSON carries arrays and plugin data the fixture may not. Copy it and
compare; never write the live vault.
