---
type: moc
title: Inbox — Personal Tasks
tags: [inbox, tasks, moc]
---

# 📌 Inbox — Personal Tasks

> Cross-entity inbox for action items extracted from meeting substrates
> (jamie + gmeet) and email. Items live inside `knowledge/people/<slug>.md`
> and `knowledge/projects/<slug>.md` entity pages — this MOC just
> aggregates them. The dashboard's `## 📌 Personal Tasks (Wiki)` section
> mirrors a slimmer view.

**Lifecycle:** the compiler reads existing State on each pass and carries
unresolved items forward; resolved items demote to Timeline with a
`[resolved]` marker when substrate evidence appears. Operator can manually
check `- [x]` to close items — that survives re-compile until next
substrate touch that confirms resolution.

---

## 🔥 Overdue (all)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects)
due before today
sort by due
short mode
```

## ⚡ Today (all)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects)
due on today
sort by priority
short mode
```

## 🗓 This week (all)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects)
due after today
due before in 7 days
sort by due
short mode
```

## 📂 No due date (all)

```tasks
not done
(path includes knowledge/people) OR (path includes knowledge/projects)
no due date
group by filename
short mode
```

---

## 🧑 By person

```tasks
not done
path includes knowledge/people
group by filename
sort by due
short mode
```

## 📁 By project

```tasks
not done
path includes knowledge/projects
group by filename
sort by due
short mode
```

---

## ✅ Recently completed

> Last 25 commitments the operator has checked off. Useful for retro
> and for spotting items that should be demoted to Timeline.

```tasks
done
(path includes knowledge/people) OR (path includes knowledge/projects)
sort by done reverse
limit 25
short mode
```
