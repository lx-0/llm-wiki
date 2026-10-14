---
milestone: M032
slice: S01
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 5
completed_tasks: 2
---

# M032-S01 -- Slice Plan

**Goal:** The desktop app has a committed screenshot harness, a modern toolchain (TypeScript 5 strict, Biome, Svelte 5 scaffold) and no template residue — every later slice can be verified visually and type-checked before it is called done.

## Tasks

- [x] T01 -- Render harness in-repo: standalone renderer build (`vite build -c vite.renderer.config.ts` with explicit `base`/`outDir` matching Forge), a stub preload exposing `window.{vault,listeners,panel,app}` from JSON fixtures (states: default / running / failed / no-access / empty), an Electron capture script (offscreen windows, `nativeTheme` light + dark, `capturePage()` per surface + panel states, requested panel height logged) → `npm run shots` writes `out/shots/*.png`.
- [x] T02 -- TypeScript 4.5 → 5.x with `strict: true`, `moduleResolution: bundler`; fix every resulting error in `src/`; `npm run typecheck` (`tsc --noEmit`) added and green; `npm test` runs typecheck + vitest.
- [ ] T03 -- Biome replaces ESLint: `biome.json` (lint + format), ESLint config/deps removed, one mechanical format commit, `npm run lint` = `biome check`; lint green.
- [ ] T04 -- Electron Forge 7.11 → 8.0 + Vite 5 → 8 (Forge 8's Vite plugin targets Vite 8; main/preload emitted as `.cjs`, `@electron/fuses` 2.x, DMG output path moved; vitest then shares the app's Vite); `npm run package` + `npm run shots` green.
- [ ] T05 -- Svelte 5 scaffold + boilerplate out: `svelte` + `@sveltejs/vite-plugin-svelte` 7 wired into the renderer config, `svelte-check` in `npm run typecheck`, a smoke component rendered through the harness; the Forge template comment in `renderer.ts` and the placeholder `package.json` metadata (name / productName / description / keywords) replaced.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- Working on `main` directly, not in a worktree: `CLAUDE_PROJECT_DIR` is unset so the ytstack skills + drift hook key on `$PWD`, the only other worktrees are stale workflow leftovers (`.claude/worktrees/wf_*`, `batch7-index-bloat`), and every verified task is pushed — continuous merge by construction.
- The old renderer modules (`renderer.ts`, `cockpit.ts`, `atlas.ts`, …) are NOT deduplicated here; S03–S05 replace them. Shared `lib/` modules are created when their first Svelte consumer lands.
