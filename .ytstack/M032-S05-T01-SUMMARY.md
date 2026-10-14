---
milestone: M032
slice: S05
task: T01
project: llm-wiki
closed: 2026-10-15T03:55:00+02:00
verification: passed
---

# M032-S05-T01 -- Summary

## Commits

Committed together with this summary under the `M032-S05-T01:` ref — `git log --grep '^M032-S05-T01'`.

## Outcome

`window.listeners.timeline(id, hours = 24)` returns `{ startMs, bucketMs, mic, system }`: one
count per local hour, oldest first, the last bin being the current hour; `null` for an unknown
listener. The main handler clamps `hours` to 1…744 and calls `getCaptureTimeline`, which reads
every `audio_chunks` row of the window per channel through `sqlite3 -readonly` (the
`lastChunkMs` julianday → epoch-ms shape with a `julianday(timestamp) >= julianday(<since>)`
filter) and hands the timestamps to the pure `bucketByHour(timesMs, nowMs, hours)` — aligned to
the operator's clock, boundary samples in the later bin, anything older than the window or past
the current hour dropped, an unreadable db yields zeros instead of a throw. The harness stub
answers the same contract from a fixture shaped like the measured live cadence (≈ 120 chunks
per channel-hour at the listener's 30 s chunking, 08–12 and 14–18, zeros overnight; the
`empty` state is all zeros).

## Deviations from plan

- None in scope. The integration test is gated by its own `LIVE_LISTENER_DB=1` rather than
  the lifecycle test's `LIVE_LISTENER_TEST` so a read-only db check never implies toggling the
  daemon.
- Live finding for the record: the operator's db holds 16 mic + 16 system chunks in the last
  30 days (newest 2026-09-24) — capture has been off for three weeks; the Overview will show
  that honestly as an empty strip, which is the point of the chart.
- Bins are a fixed hour apart from a local-hour-aligned start, so a DST switch inside the
  window shifts that day's labels by an hour — documented in code, accepted for a 24 h strip.

## Follow-ups

- T02 draws the 2 × 24 heat strip from this contract (one hue, lightness steps; tooltip per
  cell; table view).

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && LIVE_LISTENER_DB=1 npx vitest run
src/listeners/status.integration.test.ts` — passed (vitest 100 passed / 2 skipped incl. 3
`bucketByHour` cases that failed first with "bucketByHour is not a function"; tsc +
svelte-check 0 / 0; biome 0 errors, 9 legacy warnings; live run 1 passed — 720 bins per
channel, positive mic total against `~/.screenpipe/db.sqlite`; `npm run shots` 50 captures, 0
errors, 0 layout / height failures with the extended stub).
