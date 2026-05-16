---
type: moc
title: People
---

# 🧑 People MOC

Hand-curated index of person pages. Add wikilinks above the auto-list to
pin priority entries; the Dataview block below picks up everything in
`knowledge/people/` automatically.

```dataview
LIST
FROM "knowledge/people"
WHERE compile_role != "final-only"SORT file.name ASC
```
