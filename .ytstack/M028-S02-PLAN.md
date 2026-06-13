---
milestone: M028
slice: S02
project: llm-wiki
created: 2026-06-13T15:56:13+0200
revised: 2026-06-13T16:10:00+0200
status: planned
task_count: 5
completed_tasks: 0
---

# M028-S02 -- Slice Plan

**Goal:** Re-enable deletion as a safe, recoverable, opt-in operation owned by
the engine — `.trash/` instead of `rm`, per-article backup, dirty-tree guard,
gated behind an explicit signal.

> Revised after plan-eng-review (2026-06-13): the sandbox itself moved to S01.
> S02 is now purely the safe destructive-op executor — the only part that needs
> `.trash`/backup. Deletion is engine-side (the agent proposes, never deletes),
> which is what makes the safety net guaranteeable.

## Tasks

- [ ] T01 -- Extend the structured-proposal contract from S01-T03 with a **delete
  list**: the agent emits the files it judges *factually false and primarily
  about* the false claim into a parseable block; `correct_apply.py` consumes it.
  The agent never deletes — it only nominates.
- [ ] T02 -- Engine-side delete executor: move each nominated file (and its
  `index.md` row) to `.trash/<ts>/` (preserve relative path under the timestamp
  dir), never `unlink`. Runs only when the deletion gate (T03) is on. Record the
  moves so S01-T05's reporting accounts for them.
- [ ] T03 -- Deletion gate: `--allow-delete` flag on `correct_apply.py` `main()`
  + an optional fact frontmatter field `disposition: delete` read in `apply()`;
  pass `deletion_allowed: bool` into the prompt render so the agent only nominates
  deletions when permitted. Default off → supersede. Reserved for *factually
  false* content (never happened), not *outdated*.
- [ ] T04 -- Per-article backup + tree guard: `_backup_article(path)` before any
  edit (not just the fact file as today at L73/L161); refuse a deletion-enabled
  run when `ROOT_DIR` is a dirty or non-git tree unless `--force` (reuse the git
  probe from S01-T05).
- [ ] T05 -- Tests: a gated-on deletion lands the file under `.trash/<ts>/` and
  not gone; gate-off → 0 deletions even when the agent nominates; dirty-tree run
  aborts without `--force` and proceeds with it; backup exists before edit.

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
