---
milestone: M027
slice: S01
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 2
completed_tasks: 1
---

# M027-S01 -- Slice Plan

**Goal:** Land the `watched_folders` config surface and pin the answer-landing
contract -- the two upfront decisions the rest of the milestone depends on.

> **Reframed 2026-06-07** (see DECISIONS 2026-06-07). The original S01 was three
> "irreversible PII gates" (filename-masking, derived-facts policy, answer-landing).
> The operator established that **metadata is fine to index unmasked** and the
> **human-approval walk is the content/cloud gate** -- so filename-masking is
> dropped and the derived-facts policy demotes to an optional tag. Only the
> config surface and the answer-landing technical decision remain upfront.

## Tasks

- [x] T01 -- Add `personal.watched_folders` config schema (`config.py` + `config.example.yaml` + `migrations/migrate_config_keys.py`, same commit per the config-knob rule): list of `{id, kind: local|smb, path|share, include/exclude globs}`. Validation only, no scanning yet.
- [ ] T02 -- Decide + document the answer-landing contract (where the backend's distilled answer persists: curiosity-answer artifact vs. direct knowledge-write vs. daily rollup), with the reasoning on why the chosen path doesn't fight the compile-distill contract or the 3-layer agent-scope rule for `knowledge/` writes. Record in DECISIONS.md.

## Done when

All tasks `[x]` and verified via `ytstack:summarize-task`. `watched_folders`
config round-trips through the migration; the answer-landing contract is written
in DECISIONS.md concretely enough that S03/S04 can build against it.

## Notes

No PII-sanitization task -- metadata index is unmasked, the human-approval walk
(`curiosity/cli.py:_walk`) gates content (M027-CONTEXT Decisions 2026-06-07).
T02 is the one remaining upfront decision because S03 (request shape) and S04
(backend persist) both depend on it. The optional derived-fact `sensitivity:`
tag is deferred to S05.
