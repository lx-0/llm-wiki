---
milestone: M032
slice: S01
task: T05
project: llm-wiki
closed: 2026-10-14T16:55:00+02:00
verification: passed
---

# M032-S01-T05 -- Summary

## Commits

Committed together with this summary under the `M032-S01-T05:` ref — `git log --grep '^M032-S01-T05'`.

## Outcome

Svelte 5.57 compiles inside the renderer build: `@sveltejs/vite-plugin-svelte` 7.3 is in
`vite.renderer.config.ts`, `svelte.config.js` runs `vitePreprocess()`, `tsconfig.json` includes
`src/**/*.svelte`, and `npm run typecheck` is now `tsc --noEmit && svelte-check` (so `npm test`
covers component scripts too). A smoke page (`smoke.html` → `src/windows/smoke/main.ts` →
`Smoke.svelte` with a `$state` rune reading `window.vault.status()`) renders "lxw · 2,024 notes"
through the harness in light and dark — plugin wiring, TS in `<script lang="ts">`, preload access
from a component and the capture pipeline are proven end-to-end. Boilerplate is gone: the 27-line
Forge template comment in `renderer.ts`, and `package.json` now says `llm-wiki-desktop` /
`llm-wiki` / "macOS menubar companion for the llm-wiki engine" with no empty `keywords`; the
deprecated `publish` script is `release`.

## Deviations from plan

- No `types: ["svelte"]` needed — importing `mount` from `svelte` pulls in the ambient
  `*.svelte` module declarations for `tsc`.
- The smoke page is deliberately unstyled (white in both schemes); it exists to prove the
  pipeline and is deleted in S03 when Settings + Onboarding become the first real Svelte windows.

## Follow-ups

- Through the `rtk` hook, `svelte-check` output is rewritten into a terse machine format
  (`<ts> ERROR "<file>" line:col "<message>"`); the "svelte-check found N errors" summary line
  is not shown — read the exit code, not the summary. Noted in KNOWLEDGE.
- S01 is complete → `ytstack:reassess-roadmap` before S02.

## Verification

Command: `cd desktop && npm test && npm run shots … && ls out/shots/smoke-dark-default.png` —
passed (tsc + svelte-check silent, vitest 53 passed / 1 skipped, 30 captures incl.
`smoke-{light,dark}-default.png` showing the fixture name + count). Gate proven live: a
`Probe.svelte` with `const probe: number = "…"` made svelte-check report
`Type 'string' is not assignable to type 'number'` and was removed again.
