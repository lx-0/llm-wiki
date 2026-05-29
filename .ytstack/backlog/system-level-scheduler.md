# System-level scheduler (decouple piggybacks from Claude-Code sessions)

**Surfaced:** 2026-05-29 operator-observation during inbox-bridge wedge.

## The problem

Every piggyback in `flush.py` fires from a Claude Code SessionEnd hook —
the assumption being that the operator works in Claude Code most days and
the natural session boundary is a fine cadence trigger. The 2026-05-28
inbox-bridge slice surfaced the failure mode of that assumption:

> "wenn ich nicht mit claude code einen tag arbeite, wird auch nichts
> gepiggybacked"

A day (or longer) without Claude Code activity = no email scan, no
calendar pull, no gmeet/jamie ingestion, no voice transcription, no
pictures vision pass, no bridge sync, no dream cycle, no curiosity
consumer drain. The whole pipeline silently stops. Vault drift then
shows up as a knowledge-degradation event when the operator does come
back: gaps in `daily/`, stale entity pages, untranscribed voice memos,
backed-up Drive folders.

The bridge installation steps make this concrete because the bridge
SHIPS with a LaunchAgent template — every operator wiring the bridge
already touches launchd. The opportunity is to generalise that wedge:
the bridge isn't the only thing that wants a TCC-permitted,
session-decoupled scheduler — *every* piggyback does.

## Why the bridge can't fix this alone

The bridge LaunchAgent only invokes `wiki bridge sync` — it mirrors
files but doesn't ingest them. The pictures collector that consumes the
mirror is still piggyback-only, so the mirror would just stack up until
the operator opens Claude Code again. Same for every other collector.

So the bridge LaunchAgent is a half-measure: it solves the TCC problem
for one specific kind of pre-collector step but not the session-coupling
problem for the whole flush pipeline.

## Shape options

### Option A — single sweep LaunchAgent

One plist that runs `wiki flush --piggybacks-only` (new flag) on a
schedule, e.g. every hour. The flush dispatcher already knows about
per-piggyback cooldowns — it would just skip everything that isn't due,
identical behaviour to a SessionEnd-triggered flush, just on a clock
instead.

- **Pro:** one moving part. Honors existing `cooldown_hours` per
  piggyback — no schedule duplication.
- **Pro:** drop-in replacement; SessionEnd hook can stay live or be
  removed.
- **Con:** all piggybacks run in one process tree → one slow collector
  (gemma4 over 49 pictures) blocks the rest of the sweep. Today's
  flush is sequential too, so behaviourally the same, but a clock-based
  sweep is more sensitive to it because the operator isn't there to
  notice the long tail.

### Option B — per-piggyback LaunchAgent

One plist per piggyback. Each respects its own `cooldown_hours` natively
via `StartInterval`. The flush dispatcher becomes mostly redundant.

- **Pro:** parallelism for free. Long-running collectors (pictures) don't
  block fast ones (email).
- **Con:** fan-out of installs (15+ piggybacks today). Per-collector
  plist authoring is annoying; needs a `wiki scheduler install --all`
  command to template them all out at once.
- **Con:** cooldown logic now lives in two places (plist
  `StartInterval` AND `piggybacks.<name>.cooldown_hours`) and has to
  stay in sync.

### Option C — wiki-managed daemon

`wiki daemon start` spawns a Python loop process under launchd that
reads `piggybacks.*.cooldown_hours` from CONFIG and dispatches on its
own schedule. Single LaunchAgent that's `KeepAlive: true` instead of
interval-based.

- **Pro:** all cadence config stays in config.yaml.
- **Pro:** trivially extends to event-driven triggers (folder-watch
  via fsevents, mailbox push, etc.).
- **Con:** long-running process means crash recovery, memory leak
  exposure, harder to debug than fire-and-forget cron.
- **Con:** novel infrastructure compared to A/B which lean on launchd.

## Open questions

1. **Does the SessionEnd piggyback stay?** If A or C lands, the
   SessionEnd path becomes redundant (or worse — double-fires racing on
   the bridge flock + dashboard-refresh lock). Likely answer: SessionEnd
   piggybacks should become opt-out via `piggybacks.<name>.session_end:
   false`, default true, and the scheduler honors the same flag.
2. **Lock interaction.** flush.py already has dashboard-regen fcntl
   locking; pictures collector + bridge sync use their own per-step
   locks. A clock-driven sweep needs to coexist with manual `wiki collect`
   runs without piling up duplicates.
3. **Cold-start cost.** A 30-min wake of the whole vault SDK CLI is
   nontrivial — every fire pays uv-startup + dataclass-merge +
   .env-bootstrap (~1-2s). Multiplied across 15 piggybacks/day this is
   small but real. Option C amortises; A and B pay it on every fire.
4. **TCC propagation.** LaunchAgent loaded via `launchctl load` runs
   with operator-shell TCC scope. The bridge LaunchAgent already
   surfaces the macOS first-fire approval dialog; we should batch all
   permission prompts at install time (`wiki scheduler doctor`?).
5. **Cross-platform.** Linux operators get systemd timers; the abstraction
   layer should bake in the platform split, not hand-roll plists.
6. **What about Windows?** Currently no Windows operators; defer.

## Wedge for a first slice

If accepted as a milestone (probably M-shape, not ad-hoc — it touches
flush.py, registers new CLI verbs, ships per-platform install scripts,
and changes a foundational architectural assumption):

- M-S01 — `wiki flush --piggybacks-only` flag + dispatcher rework so a
  manual call drains the same set the SessionEnd hook does. Cheap, lifts
  the test surface, no platform install yet.
- M-S02 — Option A LaunchAgent template + `wiki scheduler {install,
  uninstall, status}` macOS-side commands. Documents the trade-off vs.
  SessionEnd. Operator-side test: stop using Claude Code for 2 days,
  vault stays current.
- M-S03 — systemd timer template + same CLI verbs Linux-side.
- M-S04 — observability: `wiki scheduler status` shows last-fire +
  next-fire per piggyback, surfaces stuck/skipped runs.

Defer Options B and C unless the single-sweep model proves inadequate
in dogfooding.

## Cross-refs

- `.ytstack/backlog/<bridge LaunchAgent template>` — already shipped
  as part of inbox-bridge slice (`templates/.launchd/com.llm-wiki.bridge.plist.template`).
  Becomes the second LaunchAgent the operator installs; ideally
  `wiki scheduler install` covers both.
- `.ytstack/KNOWLEDGE.md` — flush.py session-coupling assumption +
  fcntl lock interaction.
- `scripts/flush.py` — current piggyback dispatcher.
