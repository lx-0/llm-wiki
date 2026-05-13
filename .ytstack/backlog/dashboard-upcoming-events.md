# Dashboard — Upcoming Events section

**Status:** backlog. **Blocked** by calendar-collector redesign — can't ship until per-event data exists. Independent of `dashboard-action-items.md` (that one has data, ships first).

**Origin:** 2026-05-10. User wants `dashboard.md` to surface upcoming calendar events at the top so the next meetings/deadlines are visible without leaving Obsidian.

## Problem

`scripts/scan-calendar.py` currently produces **one aggregate file** per scan run: `raw/notes/calendar/calendar-overview-YYYY-MM-DD.md`, containing event counts per year. Counts only — no per-event records, no start times, no titles, no participants.

→ Dashboard cannot surface "next 5 meetings" because there is **no source of upcoming-event records** in the vault.

## What needs to change first (the precondition)

`scan-calendar.py` must emit **per-event records** with structured frontmatter so Dataview can query `start > now()`. Two shape options:

### Option A — one file per event

```
raw/notes/calendar/events/2026-05-12T1430-paperclip-sync.md
---
type: calendar-event
title: "Paperclip Sync"
start: 2026-05-12T14:30
end: 2026-05-12T15:30
calendar: "Work"
participants: ["alex@…", "chris@…"]
location: "Zoom"
recurring: false
source: thunderbird-calendar-scan
scanned_at: 2026-05-10T13:00
---
<body: description / agenda / linked notes>
```

Pros: clean Dataview surface, granular updates, naturally backlinkable (`[[2026-05-12T1430-paperclip-sync]]` from a daily).
Cons: lots of small files (could be hundreds for a multi-year history).

### Option B — one rolling file, structured list

```
raw/notes/calendar/events.md
---
type: calendar-events-rollup
last_scan: 2026-05-10T13:00
---
- start: 2026-05-12T14:30
  title: Paperclip Sync
  ...
- start: 2026-05-13T09:00
  ...
```

Pros: single file, easy to diff, simple to scan-mutate.
Cons: harder for Dataview to query (needs to parse YAML list, not native frontmatter); breaks per-event backlinking from dailies.

**Default recommendation:** Option A. Per-event files are the SSOT pattern this engine uses elsewhere (one source = one file). Per-event is also what the eventual MCP/agent integration would want to read.

### What scan-calendar would need

1. Iterate each event from Thunderbird-CalDAV (already does this — currently aggregates).
2. Filter to relevant range: maybe last 30d → next 90d. Older history doesn't need per-file unless explicitly requested.
3. Emit one file per event with the schema above. Use `start` as the natural sort key in the filename.
4. On rescan: detect deleted events (file exists but event no longer in source) → mark `deleted: true` in frontmatter or `unlink`. Be careful — calendars sometimes return partial data after auth blips, so add a "minimum n events seen" sanity check before deleting anything.
5. Existing aggregate (`calendar-overview-YYYY-MM-DD.md`) can stay as a snapshot or be retired.
6. Schedule: piggyback like `scan-email --incremental` (24h cooldown), per the Collector pattern.

## Dashboard block (after the source exists)

```dataview
TABLE WITHOUT ID
  file.link AS "Event",
  start AS "When",
  participants AS "With"
FROM "raw/notes/calendar/events"
WHERE type = "calendar-event"
  AND start > date(now)
  AND start < date(now) + dur(14 days)
SORT start ASC
LIMIT 10
```

Section heading: `## 📅 Upcoming events` placed near the top of the dashboard (in a `## 📅 Up next` umbrella alongside Action Items, if both ship together).

## Edge cases / risks

- **Recurring events**: expand to per-occurrence files within the windowed range, not the rrule master? Probably yes — Dataview can't evaluate rrule. Means more files but a simple Dataview query.
- **Time zones**: store `start` in ISO with offset, render in operator's local. Dataview `dur()` math handles this if frontmatter is ISO-8601.
- **Deleted events**: see step 4 above. Don't trust a single empty scan.
- **Privacy**: event titles + participants land in vault, syncs via iCloud. Acceptable per the engine's "vault is local + iCloud-synced" model, but worth noting in PROCESS.md.

## Non-goals

- Bidirectional sync (writing events back to Thunderbird). One-way read only.
- Per-event note backlinking automation (operator can backlink manually if useful).
- Non-Thunderbird calendar sources (Google Calendar via API, ICS feeds, etc.). Could come later as additional Collectors.

## Hard preconditions

- [ ] Decide Option A vs Option B (recommendation: A).
- [ ] scan-calendar.py refactor to per-event emission with the agreed schema.
- [ ] Piggyback configuration (cooldown, schedule).
- [ ] Then the dashboard block.

## Doc updates required (when implementing)

- `AGENTS.md` — add `raw/notes/calendar/events/` to the file-tree.
- `docs/PROCESS.md` — calendar collector section needs rewriting for the new shape.
- `templates/dashboard.md` — the block.
- `KNOWLEDGE.md` — anything non-obvious from the rrule/recurring/timezone handling.

## Cross-link

- Companion: `dashboard-action-items.md` — same dashboard surface, different data source, ships independently.
- Sibling: `architecture-deepening.md` #1 (Scan-Scripts → Collector pattern) — calendar collector should adopt the Collector base class as part of this work, killing two birds with one stone.
