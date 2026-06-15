---
type: todo
title: Working desk — running next-actions
---

# Todo

Your running next-actions list — the operator's working layer. Hand-edit freely;
your agent may read and write here too. Keep it clear and current; prune when it grows.

## ✅ Accepted tasks

> Auto-listed from `inbox/` — every record you **accept** in triage with
> `type: task` lands here (one source of truth: the record's frontmatter, no
> copy). Run them yourself or let the `orchestrate-tasks` agent execute them;
> once a task is `done`/`blocked` it drops off this list.

```dataview
TABLE WITHOUT ID
  summary AS "Task",
  confidence AS "Conf",
  detected_at AS "Added",
  file.link AS "Record"
FROM "workspace/inbox"
WHERE type = "task" AND status = "accepted"
SORT detected_at DESC
```

_Nothing here? Open `triage.html` (or run `wiki triage`), convert an intent to a
task (**→ todo**) and **accept** it._

## ⛔ Blocked

> Tasks the agent couldn't run (see each record's `## Needs clarification`).

```dataview
TABLE WITHOUT ID
  summary AS "Task",
  detected_at AS "Added",
  file.link AS "Record"
FROM "workspace/inbox"
WHERE type = "task" AND status = "blocked"
SORT detected_at DESC
```

## 📝 Free notes

Hand-maintained next-actions that aren't intent-records:

- [ ] …
