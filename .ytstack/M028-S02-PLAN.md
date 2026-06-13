---
milestone: M028
slice: S02
project: llm-wiki
created: 2026-06-13T15:56:13+0200
revised: 2026-06-13T16:10:00+0200
status: planned
task_count: 4
completed_tasks: 2
---

# M028-S02 -- Slice Plan

**Goal:** Re-enable deletion as a safe, recoverable, opt-in operation owned by
the engine — `.trash/` instead of `rm`, dirty-tree guard, gated behind an
explicit signal.

> Revised after plan-eng-review (2026-06-13): the sandbox itself moved to S01.
> S02 is now purely the safe destructive-op executor — the only part that needs
> `.trash`. Deletion is engine-side (the agent proposes, never deletes), which is
> what makes the safety net guaranteeable.
> Reassessed at the S01 boundary (2026-06-13): the original T01 ("extend the
> proposal contract with a delete list") is ALREADY DONE — T03 designed the
> contract holistically with a `deleted` key and T04's `_parse_proposed_actions`
> already extracts + shape-guards it. S02 collapses 5→4 tasks: executor, gate,
> safety guard, tests.

## Tasks

- [x] T01 -- Engine-side delete executor: a `_execute_deletes(actions, vault)` that
  moves each nominated file (and clears its `index.md` row) to `.trash/<ts>/`
  (preserving the vault-relative path under the timestamp dir), never `unlink`.
  Returns the executed list so `_divergence` accounts for it (declared+executed
  deletions are not a surprise). Runs only when the gate (T02) is on. Mirrors
  `_execute_renames`. The `deleted` list + parser already exist (S01-T03/T04).
- [x] T02 -- Deletion gate: `--allow-delete` flag on `correct_apply.py` `main()` +
  an optional fact frontmatter field `disposition: delete` read in `apply()`; pass
  the real `deletion_allowed` ("true"/"false") into the prompt render (replacing
  S01's hardcoded "false") AND guard `_execute_deletes` so nominations are ignored
  when the gate is off. Default off → supersede. Reserved for *factually false*
  content, not *outdated*.
- [ ] T03 -- Tree guard + backup: refuse a deletion-enabled run when `ROOT_DIR` is
  a dirty or non-git tree unless `--force` (reuse the `_git_delta`/git probe from
  S01-T05 — a clean git tree is what makes `.trash` + recovery trustworthy). Back
  up each article to `.trash/<ts>/` before it is removed (the move IS the backup);
  for edits, the existing git tree is the safety net under the clean-tree precondition.
- [ ] T04 -- Tests: a gated-on deletion lands the file under `.trash/<ts>/` (not
  gone, index row cleared); gate-off → 0 deletions even when the agent nominates;
  dirty-tree run aborts without `--force` and proceeds with it; `_divergence` stays
  silent for a declared+executed deletion.

## Done when

All tasks `[x]` and verified. Deletion is opt-in, recoverable (`.trash` +
backup), and refused on an unsafe tree — no destructive op is unrecoverable.

## Notes

- The `.trash/<ts>/` move is the substrate-agnostic safety net; the dirty-tree
  refusal is the cheap belt-and-suspenders guard. Both ship (T02 + T04), not
  either/or — they cover different failure modes (recoverability vs precondition).
- Because deletion is now engine-side, S01-T05's ground-truth reporting is exact
  for deletions (the engine logs every `.trash` move) — git diff only needs to
  catch the agent's Write/Edit annotations.
