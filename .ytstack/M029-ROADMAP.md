---
milestone: M029
project: llm-wiki
size: M
created: 2026-06-22T10:44:06+0200
status: planned
total_slices: 3
completed_slices: 1
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
- [ ] S02 -- Listener-lifecycle backend in-repo (launchctl start/stop + freshness probe, ported from the `sp`/watchdog logic, NOT depending on them) + the start/stop control wired through the bridge.
- [ ] S03 -- Read-only health/status window (live poll: running state, mic/sys freshness, last-capture) + macOS packaging/signing/notarization + auto-update.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done`

## Coordination note

M029 added as a **parallel milestone** (STATE.parallel_milestones) — NOT set as
`current_milestone`, because M028 is active and M021/M027 are in flight under
parallel sessions on this shared tree. Target M029 explicitly when slicing; do not
assume it is the STATE `current_milestone`.
