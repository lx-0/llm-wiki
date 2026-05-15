---
milestone: M005
slice: S05
task: T03
project: llm-wiki
closed: 2026-05-15T20:50:00Z
verification: passed
---

# M005-S05-T03 -- Summary

## Commits so far (auto-tracked)

- `bf1295a` — feat(dashboard): open-commitments stat card (M005-S05-T02). **NOT T03 work.** T02's closing commit.

## Outcome

`templates/knowledge/MOCs/inbox-tasks.md` shipped as the canonical Inbox MOC. Seven Tasks-plugin views:

1. **🔥 Overdue (all)** — due before today, sort by due
2. **⚡ Today (all)** — due on today, sort by priority
3. **🗓 This week (all)** — due in next 7 days, sort by due
4. **📂 No due date (all)** — no due date, group by filename
5. **🧑 By person** — `path includes knowledge/people`, group by filename
6. **📁 By project** — `path includes knowledge/projects`, group by filename
7. **✅ Recently completed** — last 25 done items for retro/demotion-spotting

Header explains the lifecycle in three sentences: where items come from (jamie/gmeet/email), how they evolve (carry-forward + resolution-demotion per S04 rules), how operator can close manually. Cross-references the dashboard pane and the entity pages.

Frontmatter `type: moc` so the dashboard's `## 🗂 MOCs` listing picks it up automatically — operator navigates either via dashboard pane or via MOC list.

Templates dir, so `wiki seed` will include this in new vaults; existing vaults pick it up via `wiki seed --force` (T04 verifies).

## Deviations from plan

None.

## Follow-ups

- T04 verifies templates survive `wiki seed --force` without blowing away vault customisations.

## Verification

```
test -f templates/knowledge/MOCs/inbox-tasks.md && echo OK
# → OK

grep -E "^type: moc|^## " templates/knowledge/MOCs/inbox-tasks.md | head -10
# → type: moc + 7 ## sections

grep -c 'path includes knowledge/' templates/knowledge/MOCs/inbox-tasks.md
# → 7

uv run --project . pytest -q tests/
# → 246 passed in 0.43s (unchanged)
```

Result: **passed**.
