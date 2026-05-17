---
milestone: M022
slice: S03
task: T04
project: llm-wiki
closed: operator-pending
verification: pending-live-run
---

# M022-S03-T04 — Summary (operator-pending)

## Outcome

Engineering side done. Live-migration on lxw is an operator action; the engine cannot self-verify because `voice_inbox` + `picture_inbox` point at the operator's iCloud Drive folders.

**Operator workflow:**

```bash
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lxw/
wiki update   # pulls M022 + runs config migration
uv run --project .wiki python scripts/migrations/migrate_inbox_archive.py
```

**Verify after run:**

- `ls ~/Library/.../voice_inbox/.processed/` → "No such file or directory"
- `ls ~/Library/.../picture_inbox/.processed/` → "No such file or directory"
- `ls raw/inbox-mobile/voice/ | head -5` → migrated transcripts
- `ls raw/inbox-mobile/pictures/ | head -5` → migrated PNG/JPG + per-image sidecars
- (optional) drop one new voice note from the iPhone → `wiki collect voice` → check both `raw/voice/<slug>.md` (substrate) + `raw/inbox-mobile/voice/<orig>` (audit) materialise.

## Deviations from plan

None — plan is the operator-workflow as written.

## Follow-ups

Once operator confirms T04 done, this SUMMARY's `closed:` and `verification:` fields get flipped to the real timestamp + `passed`. Until then, M022 is engineering-complete-but-operator-verification-pending per REGEL #1.

## Verification

Pending operator live-run on lxw.
