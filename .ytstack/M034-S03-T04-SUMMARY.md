---
milestone: M034
slice: S03
task: T04
project: llm-wiki
closed: 2026-10-15T23:55:00+02:00
verification: passed
---

# M034-S03-T04 -- Summary

## Commits

- `0551cfb` -- M034-S03-T04: merge and without_wiki_hooks — the bash's merge_into_config and uninstall_one filter as pure functions in core/agents.py, rendered byte-identical to its jq; nothing calls them yet
- `7bf7582` -- M034-S03-T04: planned — the merge and the uninstall as pure functions in core/agents.py

## Outcome

`core/agents.py` now holds the install and uninstall logic as two pure functions. Rendered
with `render()`, each produces the file text the bash's jq writes.

- **`merge(config, payload)`** deep-merges the top level as jq's `*` does. Per event, other
  tools' entries stay and the payload's are appended. Events keep their places, and new
  ones go at the end.
- **`without_wiki_hooks(config)`** applies T02's uninstall filter, for both entry shapes.

Both use the one grammar. Nothing calls them yet; T05's port does.

## Deviations from plan

None. Two fixture slips were fixed while the parity tests went green: the merges ran with
`ROOT_DIR` ≠ the vault, so the bash named its cloud environment after the temp directory,
and one fixture used a script name outside the grammar.

## Follow-ups

- T05 calls them from the commands, reads and backs up through `core/backup`, and writes
  through a temp file (the bash's rule).
- The bash can no longer serve as the reference once T07 deletes `lib/agents.sh`.
  `test_agents_merge.py` and `test_agents_registry.py` then compare against recorded
  expectations: the oracle's hooks goldens already hold the bytes.

## Verification

Command: `uv run --frozen pytest tests/test_agents_merge.py tests/test_agents_registry.py
-q` — passed (48). `ty check scripts/core` is clean. Full suite: 2495 passed, 1 skipped.

Seen RED on the missing functions (26 failed). Two deliberate slips, events reordered and
emptied groups kept, each failed a parity test. CI green on `0551cfb`.
