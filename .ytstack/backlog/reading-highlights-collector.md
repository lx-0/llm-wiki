# Reading highlights collector — Readwise / Kindle / Pocket / Instapaper as substrate

**Priority:** P2 — operator consumes long-form via Kindle / Pocket-style apps. Highlights are pre-curated: the operator already filtered the signal out of the noise. Currently zero wiki coverage.

**Origin:** 2026-05-15 substrate-landscape conversation. "Read-later & Highlights: Readwise, Pocket/Omnivore, Kindle Highlights" was in the original landscape.

## The gap it fills

A wiki article about a concept gains depth from "what the operator highlighted while reading X". The act of highlighting is itself filtering — operator has already said "this matters." compile.py distilling daily/ entries can't see this trail; the wiki ends up with conclusions but no source-of-thinking.

## Source landscape

| Source | Format | Access |
|---|---|---|
| Readwise | REST API `readwise.io/api/v2` | Live, Bearer token (free for read-only). Aggregates Kindle + Instapaper + Pocket + manual highlights into one stream. **The cleanest source if operator pays for Readwise.** |
| Readwise Reader (newer product) | Same API | Live | Same auth; v3 endpoints for Reader-specific content. |
| Kindle highlights direct | `~/Library/Containers/com.amazon.Kindle/Data/Documents/...` (macOS) | Local SQLite | If Kindle app installed; alternatively, `Your Highlights` page on amazon.com (HTML scrape). |
| Pocket / Omnivore | REST API | Live | Pocket sunsetting was rumored; Omnivore is the open-source successor with API. |
| Instapaper | REST API | Live, OAuth | If operator uses it; cheap to add. |
| iBooks / Apple Books | `~/Library/Containers/com.apple.iBooksX/...` SQLite | Local | Macos-only, schema reverse-engineer. |

If operator pays for Readwise: **only build the Readwise adapter** — it normalizes all upstream sources into one API. Skip per-source adapters.

## Substrate boundary

Two flavors of content from this substrate:

1. **Highlights** — short quoted passages with optional operator note. High signal. Lands in `raw/notes/highlights/<source>/<book-or-article-slug>.md` — one file per book/article, append-mode as highlights flow in.
2. **Articles read** — full read-later articles the operator saved/finished. Medium signal (saving ≠ reading). Lands in `raw/articles/` (already a wiki substrate folder).

Per-book file shape:

```yaml
---
title: "The Beginning of Infinity"
author: "David Deutsch"
source: readwise
isbn: "978-0143121350"
highlight_count: 47
last_highlight: 2026-05-12
---

## Highlight — 2026-05-12 · loc 4231
> All progress comes from creativity, not from authority.

**Note:** Echoes the gbrain dream-cycle framing — synthesis as the actual work.

## Highlight — 2026-05-10 · loc 3892
> ...
```

Operator-note fields (where present in Readwise) are first-class wiki content — they're the operator's own thinking attached to a quote. compile.py treats noted-highlights as higher-priority than bare highlights.

## Phasing

**Phase 1 — Readwise API.** If operator pays. Daily pull `/api/v2/highlights/?updated__gt=<watermark>`, group by book, append to per-book file. Lift: 0.5 day.

**Phase 2 — Kindle direct + Apple Books direct.** Only if no Readwise. SQLite walkers, drop into same shape. Lift: 1.5 days for both.

**Phase 3 — Omnivore / Pocket API.** If operator uses these and they're not aggregated by Readwise. Lift: 1 day.

**Phase 4 — Articles read substrate.** Separate from highlights — full text of read-later articles. Goes to `raw/articles/`. Lift: 0.5 day after Phase 1/3.

## Anti-slop heuristics

- Highlights that are pure formatting (single em-dash, bare URL) — drop.
- Highlight + operator-note > bare highlight in compile-stage weighting.
- Books with <3 highlights — keep but mark `engagement: low`; compile.py probably skips.
- Articles "saved but not read" (Readwise tracks reading state) — keep in `raw/articles/` but mark `read: false`.

## Multi-tenant shape

`personal.accounts.<id>.reading` with `kind: readwise-api` (or `kindle-sqlite`, `omnivore-api`, ...). Most operators have one Readwise account; multi-tenant is forward-compat, not immediately needed.

## Open questions

- **Does operator pay for Readwise?** If yes, Phase 1 only — skip the rest. If no, Phase 2 (Kindle direct) is the realistic alternative. **Decide before starting.**
- **Article full-text storage.** Read-later articles can be MB-scale of HTML. Store in `raw/articles/` as cleaned markdown, not HTML. Reuse the Readability/Mercury extractor pattern from collectors-pitch.
- **Highlight de-dup.** Re-importing a book causes Readwise to mint new highlight-ids for the same passages. Detect by `(book_id, location, text)` triple, not by `highlight_id`.
- **Source attribution.** A Readwise highlight has both `source_url` (Pocket article URL) and `book.asin` (Kindle book). compile.py needs to know which to cite.

## Touchpoints

- `scripts/collectors/reading.py` — orchestrator.
- `scripts/adapters/reading/readwise.py` — REST client.
- `scripts/adapters/reading/kindle_sqlite.py` — local Kindle DB walker (Phase 2 only).
- `state/reading-state.json` — per-source `last_updated_time` watermark.

## Lift estimate

- Phase 1 (Readwise only): **0.5 day** — if operator pays.
- Phase 2 (Kindle + Apple Books direct): **1.5 days** — if no Readwise.
- Phase 4 (full-article text to `raw/articles/`): **0.5 day** after Phase 1/3.

**~1-2 days** depending on Readwise-vs-direct decision.

## Risks

1. **Readwise paid tier dependency.** Operator might not pay. Decide up-front.
2. **Kindle DB lock during Kindle.app use.** Copy-then-read SQLite pattern.
3. **HTML extraction quality.** Read-later articles vary wildly. Readability extractor handles 90%, manual fixup on edge cases.
4. **Privacy.** Highlights themselves are public-quoted-content from books; operator-notes might be private. Default: ingest both; sensitivity flag on operator-note presence.

## Ripens when

- Operator notices that wiki articles about concepts don't link to the books that informed them.
- OR `entity-pages-state-timeline.md` lands and concept-pages want "sources" pane.
- OR `takes-substrate.md` lands and book-highlights are a natural producer of "what authors believe".

## Status

Backlog, concept-stage. Phase 1 (Readwise) is a 0.5-day "land a new substrate" win if operator pays. Decide first.

## Cross-references

- Adjacent: `takes-substrate.md` (book highlights as takes-producer for authors).
- Reference: collectors.md "Articles / RSS" row (overlapping concern).
