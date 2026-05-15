---
milestone: M006
project: llm-wiki
created: 2026-05-15T20:21:26Z
size: L
---

# M006 -- Context

## Goal

Replace the year-count `scan_calendar.py` stub with a real Google Calendar collector that lands per-date rollups in `raw/notes/calendar/<date>.md`, runs multi-tenant via `personal.accounts.<id>.calendar`, reuses the existing google_oauth infrastructure (gmail/gmeet), collapses recurring events to canonical concept pages, and cross-links events with same-window gmeet/jamie transcripts.

Origin: `.ytstack/backlog/calendar-collector.md` (P1, concept-stage). Backlog file pre-baked phasing, source landscape, anti-slop heuristics, multi-tenant shape, and risks -- this milestone consumes that pitch.

## Exit criteria

- `wiki collect calendar` ingests Google Calendar events via OAuth (scope `calendar.readonly`, token shared with gmail/gmeet) and writes `raw/notes/calendar/<date>.md` per date with frontmatter (`title`, `type: calendar-rollup`, `date`, `event_count`, `meeting_hours`, `focus_hours`, `people`, `event_ids`) + per-event body blocks.
- Multi-tenant config shape: `personal.accounts.<id>.calendar` with `kind: google-calendar`; per-account watermark in `state/calendar-state.json`. No flat `personal.calendar:` block.
- Backfill window configurable (default 90d past), future re-fetch window 7d (mutable events refreshed via `etag` / `updated` comparison).
- Multi-calendar: secondary Google calendars loop through, each event tagged `calendar: <name>` in its body block.
- Recurring-event series collapse to one canonical `knowledge/concepts/<recurring-event-name>.md`; per-date rollup just lists `[recurring: …]` reference.
- Same-time-window cross-link: post-pull pass scans `raw/transcripts/{gmeet,jamie}/` and wires `transcript: …` frontmatter into matching event blocks.
- `wiki calendar-auth <account-id>` bootstrap CLI mirrors `wiki gmail-auth`.
- Old `scan_calendar.py` (year-counts stub) removed; Registry entry replaced.
- `docs/architecture.excalidraw` + `docs/overview.excalidraw` updated to show calendar collector with the same shape as gmail/gmeet.
- Lint/tests green; `templates/.obsidian/` updated if dashboard exposes upcoming events; backlog-file moved to "shipped" memory.

## Size

L -- see `M006-ROADMAP.md` for slice breakdown. Backlog lift estimate ~2.5 days for phases 1-3, plus recurring-event collapse pulled in as its own slice = 4 slices seeded.

## Decisions locked in discuss phase

(Append decisions here as they're made during slicing + execution. Format: "YYYY-MM-DD: decided X because Y.")

- 2026-05-15: account id `default` reserved for legacy state migration -- if any pre-existing google-account already in `personal.accounts.*` will reuse its id for the calendar block, not introduce a new flat shape.
- 2026-05-15: OAuth scope is additive to existing google integrations; bootstrap CLI must support re-consent flow when an existing account upgrades from gmail/gmeet scopes to include `calendar.readonly`.
- 2026-05-15: per-date file granularity (one md per date), not per-event -- matches health-collector pattern and avoids fragmentation; per-event linkability via `event_ids` frontmatter array.

## Open questions

- Recurring-event canonical-page naming convention -- slug from `summary`? Or stable from `recurringEventId`? Slice S03 decides.
- Cross-link tolerance window -- exact overlap, or ±15 min for ad-hoc start drift? Slice S04 decides via gmeet/jamie sample inspection.
- Private-event policy -- backlog says "store title verbatim"; confirm during S01 with a real `[Private]` event from operator's calendar.
- Dashboard surfacing -- M003-S01 dashboard has `dashboard-upcoming-events.md` blocked on this redesign. In-scope for M006 or follow-up? Default: out-of-scope here, separate ticket once collector is live.
