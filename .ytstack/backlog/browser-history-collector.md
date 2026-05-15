# Browser collector — bookmarks + filtered history as substrate

**Priority:** P3 — passive consumption signal. Lower yield per row than
LLM-transcripts, but cheap and dense in research-trail context.

**Origin:** 2026-05-15 substrate-landscape conversation. Identified as the
cheapest passive ingest channel (everything sits in local SQLite, no API auth).

## The gap it fills

The operator's research trail — what they read, googled, revisited, bookmarked
— never reaches the wiki. Daily/ entries capture conclusions; browser history
captures the path. A wiki article about a concept gains depth if it knows the
operator read three specific articles before writing it.

## Source landscape

| Browser | History | Bookmarks | macOS access notes |
|---|---|---|---|
| Chrome / Arc / Brave | `~/Library/Application Support/<browser>/Default/History` (SQLite) | `Bookmarks` (JSON, same folder) | No TCC issues. File locked while browser open — copy first. |
| Safari | `~/Library/Safari/History.db` (SQLite) | `Bookmarks.plist` | Needs **Full Disk Access** in System Settings (TCC sandbox). |
| Firefox | `~/Library/Application Support/Firefox/Profiles/*/places.sqlite` | Same file (`moz_bookmarks` table) | No TCC issues. |

Chromium-family share schema: `urls` (url, title, visit_count, typed_count,
last_visit_time), `visits` (per-visit rows with `from_visit` chain for
referrer trail), `keyword_search_terms` (searches typed into the omnibox).

## Phasing

**Phase 1 — Bookmarks only.** Low volume (operator has hundreds, not millions),
high signal (curated by hand), no TCC headache (Chrome JSON is readable
anytime; Safari plist is the only TCC case). One md file per bookmark folder,
or one rollup file per browser. Frontmatter: `browser`, `folder`,
`bookmark_count`, `last_synced`.

**Phase 2 — Filtered history with quality gates.** Volume is the problem:
typical Chrome `urls` table has 50k+ rows. Aggressive filtering required (see
Anti-slop). Daily rollup file with deduped domains + revisited URLs only.

**Phase 3 — Search-term mining.** `keyword_search_terms` shows what the
operator typed into search engines — high-signal "what was I trying to find"
trail. Could be its own daily rollup.

## Anti-slop heuristics

Required for Phase 2 — without them the substrate is unusable noise:

- `typed_count > 0` — URL was typed, not clicked. Intentional navigation.
- `visit_count >= 3` — page was revisited. Operator came back to it.
- Dwell time threshold (if browser tracks it).
- Domain denylist: `localhost`, `127.0.0.1`, dev URLs, ad-tech domains.
- Domain allowlist mode: only ingest visits to operator-tagged domains
  (e.g. arxiv.org, github.com, anthropic.com, lwn.net). Probably the most
  realistic shape.
- Stop-word URL paths: `/login`, `/oauth`, `/auth/callback`, `/static/`,
  `/_next/`, `/api/` (when not the operator's own API).

## Substrate boundary

Bookmarks are curated → high-trust, ingest verbatim.
History is passive → low-trust, requires filtering, treat as supporting
evidence not standalone substrate. Lands in `raw/notes/browser/` to keep it
distinct from the operator-typed `raw/notes/` content.

## Open questions

- **Multi-machine.** Chrome syncs history across machines via Google account.
  Does the collector see the synced view, or only this-machine visits? Need to
  check the SQLite schema for a machine-id field.
- **Profile multiplicity.** Chrome can have multiple profiles (Default,
  Profile 1, Profile 2). Each is a separate History DB. Account-bound: per
  profile, treat as separate accounts in `personal.accounts.<id>.browser`.
- **Incognito.** Not in the DB by design. Substrate gap is intentional;
  document so future-you doesn't go hunting.
- **Safari worth the TCC pain?** Operator's primary browser is Arc (Chromium).
  Safari might be skippable for v1.
- **Sync vs. ingest semantics.** If the operator deletes browser history, does
  the collector also delete from the wiki? Probably no — wiki is append-only,
  browser delete = operator wanted to forget, not retro-edit the wiki.

## Touchpoints

- `scripts/collectors/browser.py` — new collector. Multi-source: enumerate
  configured browsers, pick the right schema reader per browser type.
- `scripts/adapters/browser/` — new subpackage mirroring `adapters/mailbox/`:
  `chromium.py`, `firefox.py`, `safari.py`. Each implements a shared protocol
  returning `BookmarkRow` / `HistoryRow` iterables.
- `state/browser-state.json` — per-profile `last_visit_id` watermark.
- New config: `personal.accounts.<id>.browser` with `kind: chromium|firefox|safari`,
  `profile`, `history_filter` (allowlist|denylist|both), `min_visit_count`.

## Lift estimate

- Phase 1 (Chromium bookmarks JSON walker): 0.5 day
- Phase 1 + Firefox + Safari bookmarks: 1 day
- Phase 2 (Chromium history with filters): 1-2 days
- Phase 3 (search terms): 0.5 day

**~3 days end-to-end** assuming Chrome + Firefox bookmarks for Phase 1,
Chrome history for Phase 2. Safari deferred.

## Risks

1. **Volume.** Even with filters, Phase 2 can produce dozens of rows per day.
   Mitigation: daily rollup not per-visit file; min-revisit threshold.
2. **Sensitive URL paths.** Internal company URLs with auth tokens in query
   strings, or accidentally-typed credentials. Mitigation: redact query string
   for non-allowlisted domains; default `redact_query_params=true`.
3. **DB locked while browser open.** SQLite copy-then-read pattern (`cp
   History /tmp/...` then read the copy). Document.
4. **Cross-machine duplicates.** Chrome sync means the same URL appears in
   multiple profile DBs. Mitigation: dedupe by URL + visit-day in the rollup.
5. **Pivot away from Chromium.** If operator switches to Safari, Phase 2 needs
   the TCC dance done. Mitigation: build the adapter layer cleanly so Safari
   is a drop-in.

## Ripens when

- Operator asks "what did I read about X last month?" and realizes daily/ has
  the conclusion but not the trail.
- OR Phase 1 (bookmarks) is so cheap it's a 1-day win regardless of Phase 2.
- OR llm-transcripts-collector ships and operator wants the corresponding
  "what was I reading while debugging that" cross-reference.

## Status

Backlog. Phase 1 is the easiest "land a new substrate this week" win in the
backlog — bookmarks are tiny, the schema is stable, no auth, no TCC. Phase 2
is the substantive piece and needs the anti-slop heuristics to be real, not
aspirational.
