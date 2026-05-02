# Wiki Dashboard

> Home page for the vault. Requires the **Dataview** community plugin (auto-suggested by `install.sh` via `.obsidian/community-plugins.json` — approve it on first Obsidian launch).

## Recently compiled

```dataview
TABLE file.mtime AS "Updated", file.folder AS "Folder"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log"
SORT file.mtime DESC
LIMIT 15
```

## Wiki stats

```dataview
TABLE length(rows) AS "Articles"
FROM "knowledge"
WHERE file.name != "index" AND file.name != "log"
GROUP BY file.folder
```

## Recent daily logs

```dataview
TABLE file.mtime AS "Updated"
FROM "daily"
SORT file.name DESC
LIMIT 7
```

## Recent raw additions

```dataview
TABLE file.cday AS "Added", file.folder AS "Folder"
FROM "raw"
SORT file.cday DESC
LIMIT 10
```

## Navigation

[[knowledge/index|Index]] · [[knowledge/log|Log]] · [[AGENTS|Schema]]
