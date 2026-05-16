---
type: moc
title: Concepts
---

# 💡 Concepts MOC

Hand-curated index of concept articles. Group related concepts under H2
headings above the auto-list; the Dataview block below picks up
everything in `knowledge/concepts/` automatically.

```dataview
LIST
FROM "knowledge/concepts"
WHERE compile_role != "final-only"SORT file.name ASC
```
