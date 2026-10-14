---
milestone: M032
slice: S01
task: T04
project: llm-wiki
closed: 2026-10-14T16:20:00+02:00
verification: passed
---

# M032-S01-T04 -- Summary

## Commits

Committed together with this summary under the `M032-S01-T04:` ref — `git log --grep '^M032-S01-T04'`.

## Outcome

The desktop builds on Electron Forge 8.0.1 (all nine `@electron-forge/*` packages), Vite 8.3.4
and `@electron/fuses` 2.1.3; vitest 4 now shares the app's Vite instead of nesting its own copy.
`package.json` declares `"type": "module"` and `"main": ".vite/build/main.cjs"`; the seven
`BrowserWindow` preload paths point at `preload.cjs`; the renderer config builds its seven HTML
entries from a `PAGES` list via `rolldownOptions` + `import.meta.dirname`. `npm run package`
writes `out/llm-wiki-darwin-arm64/llm-wiki.app` with `main.cjs` + `preload.cjs` inside the asar;
`npm run shots` builds the renderer on Vite 8 with zero warnings.

## Deviations from plan

- `"type": "module"` turned out to be needed after all — not for Forge, but because Vite 8's
  native config loader warns on ESM syntax in a CommonJS-loaded `.ts` config; with the package
  ESM, the `__dirname` in the renderer config became the next warning and was replaced by
  `import.meta.dirname`.
- `forge.config.ts` needed no change for fuses 2 (`FuseVersion.V1` / `FuseV1Options` kept).
- The old `.vite/build/main.js` + `preload.js` are gone (dir now holds only the `.cjs` pair).

## Follow-ups

- `scripts/dev-install.sh` still works (finds the `.app` under `out/` at depth 2); the DMG target
  moved to `out/make/dmg/<arch>/` — S05-T03 (`npm run dmg`) must look there.
- KNOWLEDGE: Forge 8 / Vite 8 bullet added to the desktop toolchain section.

## Verification

Command: `cd desktop && npm run package … && npm test && npm run shots` — passed (package exit
0, `main.cjs` + `preload.cjs` + `app.asar` present; vitest 53 passed / 1 skipped; 28 captures,
0 warnings; `biome check` 0 errors).
