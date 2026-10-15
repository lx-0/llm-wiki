---
milestone: M034
slice: S03
task: T02
project: llm-wiki
closed: 2026-10-15T23:10:00+02:00
verification: passed
---

# M034-S03-T02 -- Summary

## Commits

- `f880a16` -- M034-S03-T02: the hooks commands fixed in the bash, then recorded (release 0.7.16) — uninstall removed nothing yet said '✓ removed', a failed install said Done, a same-second backup replaced the original
- `8b936a8` -- M034-S03-T02: planned — fix the hooks commands in the bash, then record them (0.7.16)

## Outcome

The bash hooks commands now do what they report, and the oracle holds it (engine 0.7.16).

**`wiki hooks uninstall`** removes exactly the wiki's entries, by the one grammar (T01's,
which the probe and the merge use too):
- it filters `{matcher, hooks}` groups and Cursor's bare entries alike;
- groups and events the removal emptied go;
- a config with nothing of ours is not touched, with no backup;
- a config jq cannot read is reported and left as it was, with no `.tmp`.

**A failed install or uninstall** names its cause and ends `✗ n of m … failed` with exit 1;
`setup` passes that on.

**`backup_file`** never writes over an earlier backup: a clash takes `-2`, and a failed copy
stops the write.

**Five new or re-recorded goldens** pin all of this for the T03 port. The install goldens
are unchanged.

## Deviations from plan

- **A fourth defect, found while recording.** The keeps-foreign goldens showed the
  uninstall's backup as changed in one case and new in the other. `backup_file` names to
  the second, so a second backup in the same second replaced the first, which is the
  operator's pre-install original. It was fixed in the bash first, with a RED test that pins
  `date`. The two preparations drop their own backups, so the case's backup name no longer
  depends on timing.
- **The merge's unreadable-config message changed.** It no longer claims "not valid JSON"
  when jq itself could not run. No golden held the old text.

## Follow-ups

- **S03-T03 (split from the port after this task):** one Python backup helper with the
  never-overwrite rule. `core/frontmatter.backup` (correct / take) has the same
  to-the-second overwrite flaw; its callers back up once per SDK-bound run, so it is
  practically unreachable today. `dedup.py:560` hand-rolls a copy. The port (now T04)
  decides whether `hooks status` and doctor walk the hook entries (T01 follow-up).
- The "For your vault" line in 0.7.16 tells operators who ran the no-op uninstall that their
  hooks are still installed.

## Verification

Command: `uv run --frozen pytest tests/test_hooks_merge.py tests/test_bash_oracle.py
tests/test_agents_registry.py -q` — passed. Full suite 2465 passed, 1 skipped.

Seen RED first, each on the defect:
- the four `uninstall_one` tests (Claude wiki hooks left in place, Cursor foreign entry
  dropped, an untouched config rewritten with a backup, an unreadable one "removed" with
  exit 0);
- the failed-install test (exit 0 + Done);
- the backup test (same name twice).

Each new golden's change section was read. CI green on `f880a16`.
