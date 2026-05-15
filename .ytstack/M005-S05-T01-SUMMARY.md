---
milestone: M005
slice: S05
task: T01
project: llm-wiki
closed: 2026-05-15T20:25:00Z
verification: passed
---

# M005-S05-T01 -- Summary

## Outcome

`templates/dashboard.md` now carries a new `## 📌 Personal Tasks (Wiki)` section, inserted before the existing `## ✅ Open tasks` so the visual flow is engine-internal-lint → vault-working-files → **wiki-entity-commitments** → browse-knowledge. Four Tasks-plugin query blocks:

- **🔥 Overdue** — `due before today` + path-filter to `knowledge/people` ∪ `knowledge/projects`, sorted by due date, limit 20
- **⚡ Today** — `due on today`, sorted by priority
- **🗓 This week** — `due after today` AND `due before in 7 days`, sorted by due date, limit 20
- **📂 All open (no due date)** — `no due date`, grouped by folder, limit 25 — catches items the LLM extracted without a stated deadline

Section intro links to `[[knowledge/MOCs/inbox-tasks]]` (created in T03).

## Deviations from plan

None.

## Follow-ups

- T02 adds the stat-card pair.
- T03 creates the `inbox-tasks.md` MOC that this section's intro paragraph links to.
- T04 confirms templates survive `wiki seed --force`.

## Verification

```
grep -nE "^## 📌 Personal Tasks" templates/dashboard.md
# → 510:## 📌 Personal Tasks (Wiki)

grep -cE 'path includes knowledge/(people|projects)' templates/dashboard.md
# → 4 (one per Tasks block)

uv run --project . pytest -q tests/
# → 241 passed in 0.59s (unchanged — template content only)
```

Result: **passed**.
