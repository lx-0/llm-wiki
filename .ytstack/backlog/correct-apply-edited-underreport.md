# correct apply — agent under-reports `edited[]` in the proposal block

**Status:** backlog (observed live on lxw 2026-06-13, M028 verification)
**Severity:** low (no data-loss risk — edits, not deletions)

## Observation

In the live lxw apply of `senkrechtstarter-award-not-won`, the agent edited
`knowledge/people/rafael-krajewski.md` but did NOT list it in the fenced-JSON
`## Proposed actions` `edited[]` array. The engine's ground-truth filesystem
report still showed the real delta (modified: 3), so nothing was hidden — but the
agent's self-declared `edited[]` is incomplete.

## Why it's low-stakes

The M028 safety model never trusts the agent's list for *deletions* — `_divergence`
only alarms on unaccounted-for *deletions*, which are engine-executed and fully
known. Under-declared *edits* carry no data-loss risk; the git diff is the record.

## Options

1. **Prompt reinforcement** — strengthen `prompts/correct_apply.md` to "list EVERY
   file you touch with Write/Edit under `edited`, no exceptions." Cheap, partial
   (agent compliance isn't guaranteed).
2. **Derive `edited[]` from the delta** — ignore the agent's `edited`/`superseded`
   lists for reporting and compute them from the git/snapshot delta (the agent's
   lists matter only for `renamed`/`deleted` which the ENGINE executes). The
   agent's annotation lists become advisory. Cleaner — the filesystem is already
   the source of truth.
3. **Do nothing** — the ground-truth report already surfaces the real delta;
   the agent's `edited[]` is cosmetic.

Lean: option 2 if/when the reporting is revisited — `superseded`/`edited` are
informational only; `renamed`/`deleted` are the load-bearing contract.
