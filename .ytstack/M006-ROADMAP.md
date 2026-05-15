---
milestone: M006
project: llm-wiki
size: L
created: 2026-05-15T20:21:26Z
status: done
total_slices: 4
completed_slices: 4
---

# M006 Roadmap

**Goal:** Replace the year-count `scan_calendar.py` stub with a real Google Calendar collector that lands per-date rollups in `raw/notes/calendar/<date>.md`, runs multi-tenant via `personal.accounts.<id>.calendar`, reuses the gmail/gmeet OAuth infrastructure, collapses recurring events to canonical concept pages, and cross-links events with same-window gmeet/jamie transcripts.

**Exit criteria:**
- `wiki collect calendar` writes per-date rollups with full event-summary frontmatter
- Multi-tenant via `personal.accounts.<id>.calendar`, per-account watermark, no flat block
- Backfill window 90d default; 7d future re-fetch with `etag`/`updated` change detection
- Multi-calendar loop (primary + secondary Google calendars, each event tagged)
- Recurring-event series collapsed to `knowledge/concepts/<series>.md` + per-date reference
- Same-time-window cross-link with `raw/transcripts/{gmeet,jamie}/`
- `wiki calendar-auth <account-id>` bootstrap CLI
- Old stub removed; Registry entry replaced
- `docs/architecture.excalidraw` + `docs/overview.excalidraw` reflect the new collector
- Lint/tests green; backlog file moved to memory

## Slices

Slice detail lives in per-slice `M006-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 -- Phase 1 wedge: Google primary calendar via OAuth, per-date md, multi-tenant config shape, `wiki calendar-auth`, stub removal -- **shipped in single sweep with S02-S04**
- [x] S02 -- Multi-calendar loop + future-window re-fetch + etag-based mutation handling -- **shipped (selected: true default + include: override; etag map persisted; 7d future window)**
- [x] S03 -- Recurring-event collapse to canonical concept pages + per-date reference markers -- **shipped (slug persisted in state.recurring; concept-page written once per slug; per-date reference via `[[concepts/<slug>|Title]]`)**
- [x] S04 -- gmeet/jamie cross-link pass + architecture/overview diagrams + memory closeout -- **shipped (title-slug+date matcher; both excalidraw + PNGs re-rendered; DECISIONS + KNOWLEDGE entries; memory pointer)**

All four slices landed together as one M006 push (2026-05-15) — the slice plans (`M006-S##-PLAN.md`) were skipped in favour of direct implementation since the backlog file had already locked the shape. Backlog `.ytstack/backlog/calendar-collector.md` flipped to `Status: shipped`.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

Suggested initial framing (slice-milestone may refine):
- **S01** -- Phase 1 wedge: Google primary calendar via OAuth, per-date md, multi-tenant config shape, `wiki calendar-auth`, stub removal
- **S02** -- Phase 2: multi-calendar loop + future-window re-fetch + etag-based mutation handling
- **S03** -- Recurring-event collapse to canonical concept pages + per-date reference markers
- **S04** -- Phase 3: gmeet/jamie cross-link pass + architecture/overview diagrams + memory closeout

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
