---
milestone: M029
project: llm-wiki
size: M
created: 2026-06-22T10:44:06+0200
status: shipped-mvp-plus
total_slices: 3
completed_slices: 3
---

# M029 Roadmap

**Goal:** Ship the MVP of the llm-wiki Desktop App (Electron, in `desktop/`):
start/stop the screenpipe listener on the fly + a read-only health/status window.

**Exit criteria:**
- `desktop/` Electron app builds + launches on macOS as a signed, notarized `.app`.
- App control starts/stops the screenpipe listener (launchctl), verified by DB halt/resume.
- Read-only health window: running state + mic/System-Audio freshness + last-capture times, polled live.
- App consumes engine `--json` output (no scraping of human CLI text).
- Lifecycle logic ships in-repo under `desktop/`, not via `~/.screenpipe/sp`.

## Slices

Slice detail lives in per-slice `M029-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

Suggested framing (refine in slice-milestone):

- [x] S01 -- Electron scaffold in `desktop/` + engine `--json` status contract + the spawn-now/daemon-ready bridge abstraction (toolchain-isolated from the Python repo).
- [x] S02 -- Listener-lifecycle backend in-repo (launchctl start/stop + freshness probe, ported from the `sp`/watchdog logic, NOT depending on them) + the start/stop control wired through the bridge.
- [x] S03 -- Menubar panel (live health: running state, mic/sys freshness, last-capture) + DMG packaging (`npm run dmg`/`make`). **Signing/notarization is env-gated but UNUSED** (needs operator Apple Developer ID); **auto-update NOT built** (no release host) — both deferred, see below.

## Shipped beyond the MVP — 2026-06-22 (menubar GUI → CLI alternative)

The wedge grew into a real wiki frontend (operator-confirmed north star: full
GUI alternative to the `wiki` CLI for non-techies). Shipped this session:
Ask (`query --brief`, markdown + copy), What's pending (`menu --json` actionable
home), Update knowledge (`compile`, x/y), Health + Update app (`doctor --json` /
`update`), Advanced (lint/links/dedup/review), Settings (LaunchAgent autostart),
spinner+x/y on running actions, Open-in-Obsidian, brain app icon, FDA/TCC handling,
auto-fit popover. DRY: `vault/wiki-exec.ts` shared spawn; generic engine-command
runner. Full feature spec + gotchas: memory `project-desktop-app-m029`, KNOWLEDGE.md,
DECISIONS 2026-06-22, `desktop/README.md`.

## Deferred / next
- **Signing + notarization** (operator Apple Developer ID) — removes the
  right-click-to-Open Gatekeeper step; `forge.config.ts` already env-gated.
- **Auto-update** (needs a release host) — currently rebuild + reinstall DMG manually.
- **Intake actions** (ingest-youtube/html, collect) — the one meaningful command group
  not yet surfaced; admin (config/hooks/skills/setup) deliberately excluded.
- **Operator visual verification** of the GUI (rendering, FDA grant, login-cycle) — the
  parts REGEL #1 says are unverified until run in the installed DMG.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## Post-MVP arc — design + learnability (2026-06-24)

Beyond the MVP slices, the app grew to 7 surfaces (panel, Cockpit, Atlas, Triage,
Browse, Settings, Onboarding) + CLI parity (`collect`/`dream`/`triage`), then went
through a design-cohesion pass and a learnability pass (both via synthetic-user
panels). Outcome: "one authored product, shippable" (design) + blind first-run
learnability 4/10 → 6/10 (plain English, "library" not "vault", consented capture).
Full record in `.ytstack/DECISIONS.md` (2026-06-24 entry) + memory
`project-desktop-app-m029` / `feedback-synthetic-user-review-method`. **Open product
call** (declined unilaterally): radically simplify the dense panel — kept as the daily
power-surface. Headless verification: stub preload (`STUB_MODE`) + `/tmp/cap-state.js`.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done`

## Coordination note

M029 added as a **parallel milestone** (STATE.parallel_milestones) — NOT set as
`current_milestone`, because M028 is active and M021/M027 are in flight under
parallel sessions on this shared tree. Target M029 explicitly when slicing; do not
assume it is the STATE `current_milestone`.
