# 🗺️ Wiki Dashboard

> Home page for the vault. Auto-opens via the **Homepage** community plugin.
> Engine-status counts come from `_dashboard-stats.md`, regenerated as a flush-piggyback by `scripts/dashboard-stats.py`.
> The wiki's machine-facing index lives at [[knowledge/index|knowledge/index]].

## Engine status

![[_dashboard-stats]]

## Quick access

[[knowledge/index|Index]] · [[AGENTS|Schema]] · [[knowledge/log|Compile log]]

---

## Recently compiled

```dataview
TABLE WITHOUT ID
  file.link AS "Article",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Updated",
  file.folder AS "Folder",
  length(file.outlinks) AS "Out-links"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log"
SORT file.mtime DESC
LIMIT 15
```

## Top concepts

> The most-linked articles in `knowledge/`. These are the load-bearing nodes of the graph — when one of these gets stale, downstream articles drift.

```dataview
TABLE WITHOUT ID
  file.link AS "Article",
  length(file.inlinks) AS "Inlinks",
  file.folder AS "Folder"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log" AND length(file.inlinks) > 0
SORT length(file.inlinks) DESC
LIMIT 10
```

## Recent daily logs

```dataview
TABLE WITHOUT ID
  file.link AS "Day",
  dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Last session",
  file.size AS "Bytes"
FROM "daily"
SORT file.name DESC
LIMIT 7
```

## Recent raw additions

```dataview
TABLE WITHOUT ID
  file.link AS "Source",
  dateformat(file.cday, "yyyy-MM-dd") AS "Added",
  file.folder AS "Folder"
FROM "raw"
SORT file.cday DESC
LIMIT 10
```

---

> [!info] How this dashboard works
> - **Engine status** is a transclusion of `_dashboard-stats.md`, written by `scripts/dashboard-stats.py` after every `wiki flush` and before every compile.
> - The four tables below are live Dataview queries — they update as soon as files change.
> - Triage queues, charts, and topic MOCs land in later M003 slices.
