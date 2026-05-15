# Music listening collector — Spotify / Last.fm scrobbles as attention substrate

**Priority:** P3 — passive consumption signal, distinct substrate class from `sunoflow-collector.md` (which covers operator's own song *creation*). Low yield per row but cheap to ingest and useful as a mood/attention correlation channel for other substrates.

**Origin:** 2026-05-15 substrate-landscape conversation. Operator clarified that SunoFlow is creation, not listening — so a separate consumption-side collector for what they actually play is its own concern.

## The gap it fills

What the operator listens to is a mood/attention signal that no other substrate captures. Daily/ entries say what was done; LLM-transcripts say what was thought; music-listening says what was felt. compile.py can use heavy-rotation periods as a contextual ribbon underneath other substrates ("during the focus block, was on a 6-hour Brian Eno loop").

This is **never primary substrate** — nobody queries the wiki for "what music was I listening to". It's a correlation channel: weight low in distillation, surface in entity-page timeline panes only.

## Source landscape

| Source | Format | Access |
|---|---|---|
| Spotify | Web API `api.spotify.com/v1` | OAuth user-bound. `user-read-recently-played` scope (last 50 tracks rolling). `user-top-read` for monthly/yearly aggregates. **Same rolling-50 cap problem as SunoFlow play-history** — must poll often to avoid loss. |
| Last.fm | REST `ws.audioscrobbler.com/2.0/` | Free API key, unlimited history. **The cleanest source** — designed for full historical scrobble export. Operator just needs to scrobble *into* Last.fm. |
| Apple Music | Limited public API | Apple's MusicKit JS / Apple Music API — needs developer token + user token. Possible but more work. |
| Local Plex / Jellyfin | If operator self-hosts | Their APIs expose play history per user. Defer. |

**If operator already scrobbles to Last.fm:** use Last.fm exclusively. Otherwise, set up a Spotify→Last.fm scrobble bridge (free Spotify-Last.fm integration handles it automatically once accounts are linked) and ingest Last.fm.

The bridge route is unambiguously the right shape:
- One adapter (Last.fm).
- No rolling-50 cap.
- Operator-controllable cross-service (works even if operator switches Spotify→Apple Music later, as long as the new service scrobbles to Last.fm).

## Substrate boundary

Daily rollup. One md per date, `raw/notes/music/<year>/<date>.md`:

```yaml
---
title: "Music — 2026-05-15"
type: music-rollup
date: 2026-05-15
track_count: 42
unique_artists: 8
total_minutes: 167
top_artist: "Brian Eno"
top_album: "Music for Airports"
mood_signal: ambient
---

## Top artists
- Brian Eno — 18 tracks
- Tim Hecker — 8 tracks
- Stars of the Lid — 6 tracks

## Listening sessions
- 09:12–12:43 · Ambient block (29 tracks, Brian Eno × 14, Tim Hecker × 8, ...)
- 14:01–15:30 · Single album — Stars of the Lid · And Their Refinement of the Decline
```

`mood_signal` field derived from a static genre-mood map (ambient/focus/upbeat/melancholy/...). Lint can flag changes in operator's listening pattern over time.

## Phasing

**Phase 1 — Last.fm only.** Daily pull `user.getrecenttracks?from=<watermark>`. Group into sessions (gap > 30min = new session), aggregate top-artist/album, derive mood_signal from static genre map. Lift: 1 day.

**Phase 2 — Genre-mood enrichment.** Spotify `audio-features` endpoint gives valence/energy/danceability per track. Backfill onto Last.fm scrobbles by track-id resolution. Lift: 1 day. Probably defer until operator wants the enrichment.

**Phase 3 — Apple Music direct.** Only if Spotify-→Last.fm bridge doesn't cover operator's listening (e.g. AirPlay-direct-to-HomePod plays).

## Anti-slop heuristics

- Days with <10 tracks — skip (incidental background).
- Single-track-played-once — drop from "top" computations.
- Sessions <5min — drop (likely scrubbing).

## Multi-tenant shape

`personal.accounts.<id>.music` with `kind: lastfm`, `username`, `api_key_secret_ref`. Multi-tenant trivially supported but operator-side usually one account.

## Open questions

- **Does operator scrobble to Last.fm?** Needs check. If not, the setup ask is "link your Spotify to Last.fm" before any collector work — 5-min config-side setup, then this collector becomes viable.
- **Granularity.** Per-date rollup vs per-listening-session file. Per-date matches health-collector and calendar-collector pattern. Per-session would let compile.py distill specific deep-listens but is overkill.
- **Mood-signal source.** Static genre→mood map is brittle. Spotify audio-features is the proper way. Phase 1 ship with static map, Phase 2 upgrade.

## Touchpoints

- `scripts/collectors/music.py` — orchestrator.
- `scripts/adapters/music/lastfm.py` — REST client.
- `scripts/adapters/music/spotify_features.py` — Phase 2 enrichment.
- `state/music-state.json` — per-account `last_scrobble_ts`.

## Lift estimate

- Phase 1 (Last.fm + static mood): **1 day**
- Phase 2 (Spotify audio-features enrichment): **1 day**

**~2 days end-to-end.** Phase 1 alone is the realistic ship.

## Risks

1. **No Last.fm scrobbling configured.** Blocking. Operator setup before any code: link Spotify to Last.fm via Spotify's developer-tab integration (5-min, free).
2. **Spotify rolling-50 if going direct.** Same 50-track cap as SunoFlow play-history. Mitigated by bridge → Last.fm.
3. **Mood-signal noise.** Static genre→mood is wrong often. Phase 1 caveat: don't trust `mood_signal` field for distillation, only for dashboard surfacing.
4. **Privacy.** Music history is mild but real personal signal. `sensitivity: medium` frontmatter; consistent with health-collector pattern.

## Ripens when

- Operator wants "what was I listening to during the M005 sprint?" type queries.
- OR `entity-pages-state-timeline.md` lands and operator entity-page wants a "soundtrack" pane next to "physical state".
- OR distinct daily/-narrative-mood patterns emerge that operator wants correlated.

## Status

Backlog, concept-stage. Gated on Last.fm scrobbling being set up first. After that, Phase 1 is ~1 day. Always a tertiary substrate — never query-primary, always correlation-channel.

## Cross-references

- Distinct from `sunoflow-collector.md` (creation, not consumption).
- Same rolling-cap pattern as SunoFlow play-history → also blocked-by-design on Spotify direct.
- Adjacent: `health-collector.md` (both correlation-channel substrates).
