---
milestone: M029
project: llm-wiki
created: 2026-06-22T10:44:06+0200
size: M
---

# M029 -- Context

## Goal

Ship the MVP of the **llm-wiki Desktop App** — an Electron app living in a new
`desktop/` subfolder of this repo (operator decision 2026-06-22: subfolder, not a
separate repo, for now) — whose first capability is **starting/stopping the
screenpipe listener on the fly + a read-only health/status window**. NOT the full
wiki GUI; that is the expansion after this MVP proves the desktop-app direction.

Source: validated pitch `.ytstack/OFFICE-HOURS-wiki-desktop-app.md`
(office-hours → CEO-review PROCEED → eng-review GO).

## Exit criteria

- `desktop/` Electron app builds and launches on macOS as a signed + notarized
  `.app` (signing is in-scope — it is also the stable-TCC-identity fix).
- A control in the app **starts and stops the screenpipe listener** (via
  `launchctl`), verified by the listener actually halting/resuming (DB stops/
  resumes growing).
- A **read-only health window** shows, polled live: screenpipe running state +
  per-channel (mic / System-Audio) freshness + last-capture timestamps.
- The app consumes **structured output** (engine exposes `--json` on the consumed
  status/health command); it does NOT scrape human-formatted CLI text.
- Lifecycle logic (launchctl + freshness probe) ships **in-repo** under `desktop/`
  (or a future engine `listener-lifecycle` backend) — it does NOT depend on the
  operator-local `~/.screenpipe/sp` / watchdog prototypes.

## Size

M -- see `M029-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-06-22: Framework = **Electron** (operator, "no alternative"; Tauri /
  lightweight-menubar rejected). Obsidian-stack-affinity; accepted packaging cost.
- 2026-06-22: Lives as `desktop/` subfolder in llm-wiki, NOT a separate repo (can
  be extracted later).
- 2026-06-22: MVP scope reduced (SCOPE REDUCTION) to listener-toggle + read-only
  health window. Full capture/query/compile GUI is deferred expansion.
- 2026-06-22 (eng-review seams): (1) engine `--json` contract + bridge as a
  spawn-now / daemon-ready abstraction; (2) macOS signing/notarization in-scope;
  (3) lifecycle logic in-repo, app owns system-control+health lane vs Obsidian's
  browse/edit lane.

## Open questions

- Bridge final call for the MVP: child-process spawn of `wiki ... --json` /
  `launchctl` (simple, cold-start latency) vs a thin local daemon (warm, more
  surface). Lean spawn for MVP; keep the seam swappable.
- Packaging toolchain: `electron-builder` vs `electron-forge` (plan-task decision).
- Lifecycle ownership: implement launchctl + freshness probe directly in `desktop/`
  for the MVP, vs build the engine `listener-lifecycle` backend first and make the
  app a thin client. Lean app-owns-for-MVP; consolidate later.
- Cross-tech in one repo: Node/Electron `desktop/` inside a Python/CLI repo —
  decide CI / lint / build isolation so the two toolchains don't interfere.
