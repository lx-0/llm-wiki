---
milestone: M032
slice: S01
task: T02
project: llm-wiki
closed: 2026-10-14T15:00:00+02:00
verification: passed
---

# M032-S01-T02 -- Summary

## Commits

Committed together with this summary under the `M032-S01-T02:` ref — `git log --grep '^M032-S01-T02'`.

## Outcome

The desktop compiles under TypeScript 5.9.3 with `strict: true`, `target: ES2022`,
`module: ESNext`, `moduleResolution: bundler`, `isolatedModules` and `skipLibCheck`; `tsconfig.json`
no longer carries emit options (Vite owns emit). `npm run typecheck` (`tsc --noEmit`) checks the
42 files under `src/` plus the root Vite/Forge configs and is the first leg of `npm test`
(`npm run typecheck && vitest run`). The 866 phantom errors inside `node_modules` are gone with
TS 4.5; the source itself needed **zero** changes under strict.

## Deviations from plan

- No `src/**` edits were necessary — the plan budgeted for null-check and cast fixes; the
  code was already strict-clean.
- `allowJs`, `sourceMap`, `baseUrl`, `outDir` dropped from tsconfig (unused: Vite bundles,
  no JS sources).

## Follow-ups

- KNOWLEDGE "Desktop toolchain (C07)" entry rewritten: the typecheck gate is real again.
- Forge 8 / Vite 8 (T04) will switch the main bundle to `.cjs`; tsconfig needs no change for
  that.

## Verification

Command: `cd desktop && npm run typecheck && npm test` — passed (tsc silent, vitest 53
passed / 1 skipped). Gate proven live: a probe file with `const probe: number = "…"` produced
`TS2322` and was removed again.
