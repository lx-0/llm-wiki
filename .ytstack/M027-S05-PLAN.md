---
milestone: M027
slice: S05
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 3
completed_tasks: 3
---

# M027-S05 -- Slice Plan

**Goal:** The dream/compile loops fold folder-derived facts into `knowledge/`
over time, so a "what do you know about my X" query returns a folder-sourced
fact -- not just the narrative layer.

## Tasks

- [x] T01 -- Wire the folder-scan answer artifacts into compile/dream synthesis per the S01 answer-landing contract; derived facts land in the right `knowledge/` article (entity page / fact node) with as-of dates. (Chain already existed — pinned selection + email-dispatch parity, added human-readable `as_of:`; see T01-SUMMARY.)
- [x] T02 -- Apply the S01 derived-facts sensitivity policy at persist time (`sensitivity:` frontmatter; suppress what the policy excludes). (Q3 closed by operator: FULL build, marking-only — root config tag → answer stamp → compile carry; no suppression, walk stays the gate. DECISIONS 2026-06-10.)
- [x] T03 -- e2e on an lxw-shaped fixture: a folder-scan answer becomes a `knowledge/` fact; a trove-topic query (e.g. via `wiki query`) returns the folder-sourced fact with provenance. (LIVE on lxw — Hetzner invoice; 2 engine bugs found+fixed: rule-12 exemption + dedicated folder-answer dispatch.)

## Done when

All tasks `[x]` and verified. A folder-scan answer reaches `knowledge/` with
sensitivity applied, and is retrievable by topic with provenance.

## Notes

Closes the "curiosity + dream together enrich nach und nach" loop the operator
asked for. Depends on S04 (answers exist) and S01 (sensitivity + landing
contract). Exit criterion #6.
