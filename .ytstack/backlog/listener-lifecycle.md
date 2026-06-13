---
title: Listener lifecycle subsystem — manage long-running capture daemons via wiki CLI
status: concept (office-hours pending)
captured: 2026-06-13
related: [[screenpipe-intake]], [[system-level-scheduler]], [[interactive-cli]], [[collectors]]
---

# Listener lifecycle subsystem

## Premise

Operator-surfaced 2026-06-13 while running screenpipe as the first
always-on capture daemon: *"perspektivisch haben wir später mehr listener"* —
start/stop them from the `wiki` main menu, set up the autostarter, and have a
status check that they're running / installed.

A **listener** is a long-running capture *daemon* (screenpipe today; future
candidates: a clipboard watcher, a local audio recorder, a folder fswatch
daemon) — distinct from a **collector** (a script that pulls data into `raw/`
on a cadence) and from the **scheduler** (which *triggers* periodic jobs). The
engine has no concept for "an external long-running process the wiki depends
on, that must be installed, kept alive, and observable". screenpipe exposed the
gap: setup is currently a hand-built `.app` bundle + two LaunchAgents
(`com.alex.screenpipe`, `com.alex.screenpipe-watchdog`) + a hand-written
`~/.screenpipe/sp` control script — all operator-local, none of it in the
engine.

## What the operator asked for (concrete requirements)

1. **Lifecycle control in the `wiki` main menu** (`top_menu()`): start / stop /
   restart a listener — not just screenpipe, a uniform action over a registry
   of listeners.
2. **Autostart provisioning** — a command that *installs* the autostarter
   (generates + loads the LaunchAgent) for a listener, so the operator doesn't
   hand-write plists. (Mirror of how the inbox-bridge ships a LaunchAgent
   template — generalise it.)
3. **Status / health check** — "is it running AND is it set up?" surfaced
   somewhere visible (menu + `wiki status` / a doctor-style line). Two
   independent axes: *installed* (LaunchAgent present + enabled) and *alive*
   (process up + producing fresh data).

## Design seeds (not decisions — for office-hours)

- **Listener registry.** A declarative list (config or a `listeners/` dir):
  per entry `{id, label, launch_agent_label, plist_template, health_probe}`.
  The CLI lifecycle verbs operate generically over the registry; screenpipe is
  the first entry, not a special case.
- **Health probe is per-listener.** screenpipe's is "newest audio chunk fresh
  AND both device channels present" (see `~/.screenpipe/watchdog.sh` logic —
  the sleep/wake zombie check). The subsystem should let each listener declare
  its own freshness probe, not assume "process up = healthy" (screenpipe is the
  proof: process up, System-Audio stream dead).
- **Shared LaunchAgent-provisioning core with `system-level-scheduler.md`.**
  Both generate + load/unload LaunchAgents from templates. Likely one
  `core/launchagent.py` (render template → write `~/Library/LaunchAgents/` →
  bootstrap/bootout) used by both the scheduler (periodic jobs) and listeners
  (daemons). Don't build two.
- **TCC reality (hard, from screenpipe).** Some listeners need TCC grants
  (Screen/Mic) that only attach to a signed `.app` bundle, not a bare binary,
  and can't be granted by script (SIP). The "install autostarter" flow must
  surface the manual grant steps it cannot automate, and the health check must
  distinguish "not installed" from "installed but ungranted" from "granted but
  zombie". Full gotcha: `screenpipe-intake.md` §"The fix".
- **macOS-first, but keep the seam portable** — `system-level-scheduler.md`
  already flags launchd (macOS) vs systemd-timer (Linux); same split here.

## Relationship to other items

- **`screenpipe-intake.md`** — screenpipe is the first listener AND the first
  user of this subsystem. The collector (data → `knowledge/`) and the listener
  lifecycle (keep the daemon alive) are two halves of "screenpipe as a wiki
  substrate" — likely the same milestone, two slices.
- **`system-level-scheduler.md`** — sibling; shares the LaunchAgent core.
  Sequence them together so the core isn't built twice.
- **`interactive-cli.md`** — the menu surface the lifecycle actions live in.
- **`collectors.md`** — taxonomy: collector vs listener vs scheduler.

## Interim (shipped 2026-06-13, operator-local, NOT engine)

Until this subsystem exists, screenpipe is controlled by `~/.screenpipe/sp`
(`stop|start|restart|status`, wraps `launchctl bootout/bootstrap/kickstart` +
an audio-freshness status line) and kept alive across sleep/wake by
`~/.screenpipe/watchdog.sh` + `com.alex.screenpipe-watchdog`. These are the
hand-built prototypes the engine subsystem should generalise and replace.

## Next step

Not a milestone yet. Route through `office-hours` — probably folded into the
screenpipe-collector milestone as a dedicated "listener lifecycle" slice, since
screenpipe is the forcing case for both halves.
