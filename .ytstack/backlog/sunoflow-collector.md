# sunoflow collector — own music generations + listening as substrate

**Status: backlog (2026-05-15).** Conceived during the self-cartography substrate
review. Two substrate classes covered by one SunoFlow instance — kept in one
backlog entry because the wedge is the same API surface, but they ship in two
phases gated by upstream.

**Priority:** P3 — new substrate, the operator already produces it (SunoFlow
account active at `sunoflow.up.railway.app`), nothing pulls it into the vault.
Below jamie/gmeet/email priority; above DM-ingest experimentation.

**Origin:** 2026-05-15 substrate-landscape conversation. After enumerating the
DM/browser/calendar/code-activity gaps, operator pointed at SunoFlow as a
ready-to-tap channel. REST API verified against the `lx-0/SunoFlow` working
tree the same day.

## What

New registered Collector `scripts/collectors/sunoflow.py` — structurally close
to the `youtube` / `jamie` precedent, account-bound from day one per the
multi-tenant policy (no flat `personal.sunoflow` block ever).

- `SPEC.name = "sunoflow"`, `piggyback_default=True`, `piggyback_cooldown_hours=12`
  (low-churn — generations happen in bursts, no need to poll hourly).
- `SunoflowConfig` dataclass nested under `personal.accounts.<id>.sunoflow` with
  `kind: sunoflow-api`. Fields: `api_key` (Bearer `sk-…`), `instance_url`
  (default `https://sunoflow.up.railway.app`), optional `min_rating` quality gate.
- Two outputs (different substrate classes — see Phasing below):
  - `raw/notes/sunoflow/<song-id>.md` — own song generations (output substrate)
  - `raw/notes/sunoflow-plays/<date>.md` — daily listening rollup (consumption
    substrate, phase 2)
- State file `state/sunoflow-state.json` carrying `last_song_created_at` (ISO 8601)
  per account.
- One Registry wiring line: `from . import sunoflow` in `collectors/__init__.py`.

## Why

Two distinct signals the wiki currently has zero coverage of:

1. **Creative output** — what the operator composed, with which prompts/lyrics/
   tags/model. Complements GitHub commits as another "what did I make" trail.
   Tags + lyrics + chosen style are high-signal for distillation: they reveal
   moods/themes the operator iterated on.
2. **Attention** — which songs the operator actually played back (consumption
   signal, parallel to a future Spotify/Last.fm collector).

Both are useful for compile.py — generation prompts and play-favorites surface
preoccupations the operator wouldn't write down in notes.

## API map (verified 2026-05-15 against `lx-0/SunoFlow` working tree)

All endpoints `Bearer sk-…` auth. Verified at the working tree, not just the MCP
skill doc (the MCP skill exposes a strict subset).

| Endpoint | Use |
|---|---|
| `GET /api/songs?dateFrom=&dateTo=&sortBy=newest&cursor=` | Delta-ingest watermark on `createdAt`. Cursor-paginated. (`src/app/api/songs/route.ts:59`) |
| `GET /api/songs/[id]` | Full song detail: lyrics, prompt, style, model, tags, rating, audioUrl. ETag-cacheable. |
| `GET /api/playlists` + `/api/playlists/[id]` | Playlist memberships (MCP gap — REST has it). |
| `GET /api/analytics/user` | Dashboard rollup: `totalGenerations`, `dailyGenerations[]` time-series, `genreBreakdown[]`, `topSongs[]`. (`src/lib/analytics-data/user-dashboard.ts:88`) |
| `GET /api/analytics/songs/[songId]` | Per-song play/view telemetry. |
| `GET /api/streaks` | Generation streak counter. |
| `GET /api/credits` | Monthly usage snapshot. |
| `GET /api/history` | **BLOCKED — see Phasing.** Play timeline, cursor-paginated. |

## Phasing

**Phase 1 — Output substrate (ready to ship).**
Walk `GET /api/songs` with `dateFrom=<watermark>&sortBy=oldest&cursor=…` until
exhausted. One markdown file per song:

- Frontmatter: `song_id`, `title`, `created_at`, `model`, `style`, `tags`,
  `rating`, `is_favorite`, `download_count`, `playlists: [...]`, `audio_url`.
- Body: prompt + lyrics, structural tags preserved (`[Verse]` / `[Chorus]`).
- Quality gate: skip songs where `generationStatus !== "ready"`. Operator-tunable
  `min_rating` filter for compile-stage attention budget. `is_favorite` and
  `rating >= 4` are good "this one mattered" heuristics.

**Phase 2 — Consumption substrate (blocked on upstream).**
`/api/history` is currently a rolling 50-row window — `MAX_HISTORY = 50` in
`src/lib/history/index.ts:5` actively deletes everything past row 50 on each
new play, and has no date-range filter. Filed `lx-0/SunoFlow#70` requesting
both fixes (cap removal + `dateFrom` / `dateTo` range mirroring
`/api/songs?dateFrom=&dateTo=`). Range, not just `since=`, so chunked backfill
and idempotent repair runs work; same filter vocabulary as the songs endpoint.
Phase 2 ships only after #70 lands; daily rollup file per date with
`{ song_id, title, played_at, rating }` rows.

## Anti-slop heuristics

Already in the API, no LLM step needed: `rating` (1–5), `downloadCount`,
`isFavorite`. Use a multi-signal filter at compile-time (`rating >= 4 OR
is_favorite OR downloadCount > 0`) so throwaway generations don't pollute the
distilled wiki. Tag-based filters (`genre`, `mood`) available for future
narrower compile passes.

## Decided open question

Operator confirmed (2026-05-15) that SunoFlow is **creation** (own output),
which is a different axis than passive listening (Spotify/Last.fm). Both are
legitimate substrates; this collector covers the SunoFlow side only.

## Deferred / not in scope

- **Stem files / WAV / MIDI / cover art / music videos.** These are post-
  processing artefacts of individual songs, not substrate signal. The song's
  prompt + lyrics + tags already capture the operator's intent. Skipping
  audio-blob mirroring keeps the substrate purely textual.
- **Inspiration feed** (`sunoflow://feed/inspiration`). External RSS-driven
  feed, not operator-generated — wrong substrate class for self-cartography.
- **Cross-account de-dup.** Unlike gmeet (same meeting from two attendee
  accounts), SunoFlow songs are user-bound; no cross-account collision risk.

## Acceptance — Phase 1

- `wiki collect sunoflow --account <id>` writes new `raw/notes/sunoflow/*.md`
  for songs created since the watermark, advances watermark on success only
  (per `MailboxReadError`-style watermark-on-failure rule).
- A piggyback run from any other collector picks sunoflow up after the 12h
  cooldown.
- compile.py distills SunoFlow songs into wiki articles without separate prompt
  tuning — verify on first real compile pass like jamie.

## Acceptance — Phase 2

- `lx-0/SunoFlow#70` merged and deployed.
- Daily play-history rollup ingests cleanly with `since=` filter, no
  duplicate plays across collector runs.

## Cross-references

- Upstream issue: https://github.com/lx-0/SunoFlow/issues/70
- Multi-tenant policy: `feedback_account_adapters_multi_tenant` (no flat
  `personal.sunoflow` block — go straight to per-account from day one).
- Reference collectors: `scripts/collectors/jamie.py`, `scripts/collectors/youtube.py`.
