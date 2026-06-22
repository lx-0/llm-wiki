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
- 2026-06-22 (DRY re-scope of S01-T02, operator prompt "refactor sustainably"):
  **Listener status is SYSTEM data (launchd + `~/.screenpipe/db.sqlite`), not
  wiki-engine data** → the app reads it directly in TS; **no Python `wiki --json`
  command for the MVP**, no engine config/migration, no cold-spawn. The engine
  `--json` contract (eng-review seam 1) is deferred to the full-GUI expansion,
  when the app consumes wiki-PIPELINE health (compile/dream/collector) — YAGNI now.
  Listener-status logic is implemented **once** in `desktop/` as the single source
  of truth for S02 (toggle state) + S03 (health window); `sp`/watchdog stay
  disposable prototypes. Db-path/launchd-label live in a small in-`desktop/`
  **listener registry** (one entry: screenpipe), prefiguring the
  `listener-lifecycle` registry — not hardcoded.
- 2026-06-22: Packaging toolchain = **electron-forge** (research-gated via
  context7 in S01-T01: scaffold cmd + osxSign/osxNotarize confirmed).
- 2026-06-22: Test runner = **vitest** (org standard per CLAUDE.md; integrates
  with the scaffold's vite).

## Open questions

- Bridge for the MVP: in-process TS status module (decided above); the
  spawn-now/daemon-ready abstraction is retained only for *future* engine calls
  (pipeline health), not needed for listener status.
- Cross-tech CI: Node/Electron `desktop/` inside a Python/CLI repo — collection-
  level isolation holds (pytest testpaths=tests, ruff .py-only); revisit if a
  repo-wide pre-commit hook is added.
- Cross-tech in one repo: Node/Electron `desktop/` inside a Python/CLI repo —
  decide CI / lint / build isolation so the two toolchains don't interfere.
