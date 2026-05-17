---
milestone: M022
slice: S03
task: T04
project: llm-wiki
closed: 2026-05-17T15:44:41Z
verification: passed
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


## Live-run outcome (2026-05-17T15:44:41Z)

Operator authorised; executed against lxw vault.

```
voice:    moved 29 files → raw/inbox-mobile/voice (0 collisions)
pictures: moved 18 files → raw/inbox-mobile/pictures (0 collisions resolved)
both .processed/ folders rmdir-ed (removed empty)
```

**Verified post-run:**
- `<voice_inbox>/.processed/` → "No such file or directory" ✓
- `<picture_inbox>/.processed/` → "No such file or directory" ✓
- `raw/inbox-mobile/voice/` → 29 files (matches dry-run plan) ✓
- `raw/inbox-mobile/pictures/` → 18 files (9 .jpeg + 9 per-image sidecar .md) ✓

M022 closes: engineering DONE + operator live-run DONE. Mobile-collectors next run will write archive directly to vault, no more iCloud .processed/ involvement.

## Commits so far
- `e8d21eb` -- feat(cli): fail-closed vault guard — refuse to run outside Obsidian vault (2026-05-17T15:45:12Z)
- `fe65db9` -- fix(M019): 3-attempt retry + skip-and-flag for stubborn instrument failures (2026-05-17T15:41:06Z)
- `2602ff9` -- fix(M019): extend retry-once to schema-validation failures (2026-05-17T15:34:12Z)
- `2aa4636` -- feat(M019+): add ISI + OLBI instruments tuned to run-1+2 findings (2026-05-17T15:30:05Z)
- `77d29ed` -- feat(health): per-account OAuth-token check (gmail / gmeet / calendar) (2026-05-17T15:26:35Z)
- `bbf49de` -- docs(architecture): update process-inbox pill for M022 two-zone routing (2026-05-17T15:25:38Z)
- `8a80de1` -- docs(AGENTS.example): document M019 operator-self-reports surface (2026-05-17T15:24:32Z)
- `b6cadaa` -- fix(compile): classify substrate shape before LLM call (2026-05-17T15:23:38Z)
- `749e926` -- docs(diagrams): overview pill row reflects post-rebalance composition (2026-05-17T15:19:27Z)
- `b179fcb` -- fix(render_summary): register PSS-10 max-total in SLUG_TO_MAX (2026-05-17T15:08:12Z)

- `eabac90` -- M022-S03: close out engineering — T01/T02/T03 SUMMARYs + T04 operator-pending (2026-05-17T15:06:17Z)
