---
milestone: M028
slice: S03
project: llm-wiki
created: 2026-06-13T15:56:13+0200
status: done
task_count: 3
completed_tasks: 3
---

# M028-S03 -- Slice Plan

**Goal:** `--dry-run` shows the real blast radius (candidate files + planned
per-file action) before any paid call, and over-broad terms get caught at
`correct add` time.

## Tasks

- [x] T01 -- Make `--dry-run` informative in `correct_apply.py` (today L101-108
  only logs model + negation_terms): run the same greps the agent would —
  `negation_terms` (case-insensitive) across `knowledge/` + `daily/` — list each
  candidate file with its planned action (supersede / edit / delete-if-opt-in /
  rename), distinguishing "primarily about" vs "one of many mentions" by a simple
  heuristic (term in title/H1/slug vs body-only). Print counts. No agent spawned.
- [x] T02 -- Over-broad-term warning at `correct add` time in
  `scripts/facts/correct.py` `cmd_add()`: after writing the fact, grep
  `knowledge/` for each `negation_term`; when a term matches more than
  `correct_broad_term_threshold` articles (new config knob, default ~15,
  migration same-commit), print "term X matches N articles — narrow it?". Warn,
  don't block.
- [x] T03 -- Tests: dry-run lists candidate files + per-file action without
  constructing the SDK client (assert `query` never called); the broad-term
  warning fires above threshold and stays silent below it.

## Done when

All tasks marked `[x]` and verified. The operator can see exactly which files a
fact would touch — and what would happen to each — before spending, and gets
warned about over-broad terms when adding.

## Notes

- T01 shares the candidate-grep + primarily-about heuristic with the S01 prompt's
  per-file action decision. Factor the heuristic into a pure helper both the
  dry-run (Python-side) and the test can call; the live run still delegates the
  final call to the agent, but the dry-run preview should match its logic closely.
- Issue #5's secondary suggestion (broad-term detection) lands here as T02 rather
  than as a separate backlog item, per the CONTEXT open-question resolution.
