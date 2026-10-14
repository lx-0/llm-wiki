---
milestone: M032
project: llm-wiki
created: 2026-10-14T13:10:00+02:00
size: L
---

# M032 -- Context (Desktop de-slop)

Source pitch + full audit: `.ytstack/backlog/deslop-arc.md`. Goal, exit criteria and
size below are derived from the operator's request of 2026-10-14 and that audit — not
from a Q/A session — so the first review of this file is the operator's chance to
re-cut them.

## Goal

The desktop app stops reading as vibe-coded: the panel shows state as shapes instead of
sentences, every engine action appears exactly once with the verb the engine declares,
the glow/HUD costume is gone, and the renderer is rebuilt on a real component model with
a modern toolchain and a committed screenshot harness — so the operator opens the menubar
and sees, in one glance and without scrolling, what the wiki knows, how it is doing, and
what needs them.

## Exit criteria

1. **Panel:** at rest ≤ 640 px (`PANEL_MAX_H`) with zero scrolling and zero paragraphs;
   header navigation labeled; no hint banner, no raw vault path, no emoji icons; tooltips
   ≤ 6 words. Measured by the harness (requested height logged) and the screenshot gate.
2. **One action model:** doctor checks, menu suggestions and advanced commands render
   through one `Action` list; every engine action appears once with one verb. The regex /
   map vocabulary layers (`friendlyHealth`, `friendlyPending`, `pendingVerb`) are deleted;
   `wiki menu --json` and `wiki doctor --json` carry `title`, `verb`, `group`, `argv`
   (+ `schema` version), consumed verbatim by the app and reused by the TUI.
3. **Visual feedback:** Library (count + 14-day sparkline), Health (ring) and Capture
   (level meter + state word) are glyph tiles; a running action shows progress on its own
   row; done/failed leaves a persistent result pill with detail one click away.
4. **Overview window** with four real charts replaces Cockpit and Atlas; both canvases
   and their CSS are deleted in the same commit (no soft deprecation).
5. **Design system:** all colour/space/radius/type values are tokens; one type-palette
   source; light and dark correct on every window (Triage/Settings light-mode defect fixed);
   no `radial-gradient` glow, `backdrop-filter` stacks, HUD monospace labels or sparkles.
6. **Code:** TypeScript 5.x with `strict`, `tsc --noEmit` green and part of `npm test`;
   Biome replaces ESLint; template boilerplate removed; one `escapeHtml`/`fmtAgo`/logo;
   renderer modules ≤ 300 LOC; renderer has unit tests for the action model and the
   status derivations.
7. **Harness committed** (`desktop/scripts/render-surfaces` + fixtures) producing every
   surface × light/dark × panel states; the three-gate PNG review (overlap, overflow,
   zoom-crop) runs before any slice is called done.
8. **Blind synthetic learnability ≥ 8/10** (M029 closed at 6/10) and an operator look at
   the rebuilt DMG after each slice.

## Size

L -- 5 slices, see `M032-ROADMAP.md`. Expect the split check after slicing: if S03–S05
grow past 7 tasks each, S05 becomes M032b.

## Decisions locked in discuss phase

- 2026-10-14: "the app" = `desktop/`; TUI and CLI help are out of M032 (compact already) —
  see `deslop-arc.md` §8.
- 2026-10-14: The DECISIONS 2026-06-24 locks "shared atmosphere glow", "dense panel not
  gutted" and "HUD labels cockpit-only" are reopened by this milestone; "app speaks plain
  English" is kept with the mechanism moved into the engine's JSON contract. A DECISIONS
  entry records this at closeout.
- 2026-10-14: Engine-side change in this milestone is limited to the `--json` contract of
  `menu` and `doctor` (+ the TUI consuming the same `title`); no config knob is added, so
  no migration is required. Everything else engine-side waits for M033.

- 2026-10-14: Operator go ("arbeite den plan komplett ab") on the recommendations:
  **Svelte 5** for the renderer (scaffold lands in S01, not S03); **Cockpit + Atlas are
  deleted** in favour of the Overview window; **Biome** replaces ESLint for the desktop.
  Execution runs on `main` with per-task pushes (no active parallel session; ytstack keys
  on `$PWD`).

## Open questions

(none — the three framework/surface/tooling questions were decided 2026-10-14, see above.)
