# Calendar collector — Google/Apple Calendar events as substrate

**Priority:** P1 — already listed as "high" in `collectors.md` index; complements gmeet/jamie (which only see meetings with notes). Calendar gives full schedule context: who, when, where, how often, with whom.

**Origin:** 2026-05-15 substrate-landscape second-wave sweep. Existing `collectors.md` row from the original collectors-pitch.

## The gap it fills

gmeet + jamie cover meetings *with transcripts*. Calendar covers **every** event the operator scheduled — including focus blocks, 1:1s without notetaker, travel days, blocked-for-deep-work hours. Without it the wiki sees only the post-hoc digest of meetings that happened to be recorded.

Calendar also surfaces recurring patterns (weekly syncs, monthly business reviews) that compile.py can attach to person-pages and project-pages as "cadence".

## Source landscape

| Source | Format | Access |
|---|---|---|
| Google Calendar | REST API `calendar.googleapis.com/calendar/v3` | OAuth — reuse `core/google_oauth.py` from gmail/gmeet. Scope `calendar.readonly`. |
| Apple Calendar | CalDAV / EventKit | macOS sqlite at `~/Library/Calendars/Calendar.sqlitedb` (read-only), OR EventKit via Swift bridge. Probably skip in Phase 1. |
| Outlook / Exchange | EWS / Microsoft Graph | Defer — operator's primary is Google. |

## Substrate boundary

Attention substrate (planned vs actual). Lands in `raw/notes/calendar/<date>.md` — daily rollup, one file per date:

```yaml
---
title: "Calendar — 2026-05-15"
type: calendar-rollup
date: 2026-05-15
event_count: 7
meeting_hours: 4.5
focus_hours: 3.0
people: [jane-doe, bob-smith, ...]
---

## 09:00–09:30 · Standup
Attendees: jane-doe, bob-smith. Recurring. Location: Meet link.

## 10:00–12:00 · Focus block
Solo. Title-only.

## 14:00–15:00 · 1:1 with Jane
...
```

Pair across substrates: if `raw/transcripts/jamie/` or `raw/transcripts/gmeet/` has a file from the same hour, calendar event cross-links it via `transcript: ../gmeet/<file>.md` frontmatter.

## Phasing

**Phase 1 — Google Calendar primary calendar only.** OAuth via existing infra, daily pull of events `timeMin=<watermark>&timeMax=<now>`. One md per date with summary frontmatter + events list. Lift: 1 day.

**Phase 2 — Multi-calendar.** Operator has multiple Google calendars (work, personal, shared). Loop, tag each event with `calendar: <name>`. Lift: 0.5 day.

**Phase 3 — Cross-link with gmeet/jamie.** Post-pull pass that scans `raw/transcripts/{gmeet,jamie}/` for matching time windows and wires `transcript: …` into calendar event blocks. Lift: 1 day.

**Phase 4 — Apple Calendar fallback.** Only if operator starts using non-Google for some events.

## Anti-slop heuristics

- Skip declined events (`responseStatus: declined` for operator).
- Skip all-day "blocking" events with no attendees (vacation markers OK as separate frontmatter field, but don't fill the body).
- Skip cancelled events (`status: cancelled`).
- Collapse recurring-event series — write one canonical body per series in `knowledge/concepts/<recurring-event-name>.md`, daily rollup just lists "[recurring: Weekly 1:1 with Jane]".

## Multi-tenant shape

`personal.accounts.<id>.calendar` with `kind: google-calendar`, OAuth-shared with existing google integrations (one token covers gmail + gmeet + calendar scopes).

## Open questions

- **Past vs future window.** Backfill how many days? Probably 90, configurable. Future events also useful for "what's coming up" pane on dashboard — but those are mutable (events get moved/cancelled), so re-fetch window of next 7 days every run.
- **Mutable past events.** Someone updates last week's meeting title. Detect via etag/updated-time on each event; re-write file on change.
- **Private event titles.** Some calendars have "[Private] …" titles where details are hidden. Default: store the title verbatim including the marker; don't try to enrich.
- **Granularity.** One file per date OR one file per event? Per-date is simpler and matches health-collector pattern. Per-event would let entity-pages link directly. Probably per-date with `event_ids: [...]` frontmatter for grep-find.

## Touchpoints

- `scripts/collectors/calendar.py` — orchestrator.
- `scripts/adapters/calendar/google.py` — REST client, shares OAuth with gmail/gmeet.
- `state/calendar-state.json` — per-account `last_updated_time`.
- `wiki calendar-auth <account-id>` — bootstrap CLI mirroring `wiki gmail-auth`.

## Lift estimate

- Phase 1 (Google primary calendar, daily files): **1 day**
- Phase 2 (multi-calendar): **0.5 day**
- Phase 3 (gmeet/jamie cross-link): **1 day**

**~2.5 days end-to-end** for Phase 1-3. Phase 1 alone covers ~70% of the value.

## Risks

1. **Recurring-event explosion.** Daily standup × 365 = 365 entries. Mitigation: collapse to canonical concepts/page + per-date reference.
2. **Token scope drift.** Adding calendar scope to an existing OAuth token requires re-auth. Document the migration step.
3. **Mutable events overwrite operator notes.** If operator adds prose to a generated calendar-rollup file, next collector run could overwrite. Mitigation: explicit no-overwrite rule (collector only writes new files; mutates only via `events_updated` frontmatter bump, body preserved).

## Ripens when

- Operator wants daily-rollup to include calendar context alongside daily/ entries.
- OR jamie/gmeet coverage feels incomplete because "what about all the meetings without transcripts?"
- OR `entity-pages-state-timeline.md` lands and person-pages want a "recent interactions" pane that includes non-recorded 1:1s.

## Status

Backlog, concept-stage. Existing `collectors.md` row promoted to a deep file. OAuth infrastructure already in place — Phase 1 is mostly REST-client + watermark plumbing.
