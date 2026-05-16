---
type: moc
title: Projects
---

# 🚀 Projects MOC

Hand-curated index of project pages. Add wikilinks above the auto-list to
pin active projects; the Dataview block below picks up everything in
`knowledge/projects/` automatically.

```dataview
LIST
FROM "knowledge/projects"
WHERE compile_role != "final-only"SORT file.name ASC
```
