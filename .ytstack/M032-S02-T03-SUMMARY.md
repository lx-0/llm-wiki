---
milestone: M032
slice: S02
task: T03
project: llm-wiki
closed: 2026-10-14T18:55:00+02:00
verification: passed
---

# M032-S02-T03 -- Summary

## Commits

Committed together with this summary under the `M032-S02-T03:` ref — `git log --grep '^M032-S02-T03'`.

## Outcome

`desktop/src/lib/actions.ts` is the one action model: schema-2 input types for doctor checks,
menu suggestions and tools, `mergeActions()` (one row per argv; menu title/verb/count win the
visible fields, doctor severity wins the urgency, `sources` records who contributed; order
critical → warning → do → review → auto → tools, engine order within) and `withRunState()`
(pure overlay: `idle` / `running` / `done` / `failed`). Eight vitest cases pin the rules,
including the regression that mattered — the dream action that rendered three times now
collapses to one row. Engine side: the `tools` list stays non-destructive like the old
`ENGINE_COMMANDS` were (`links` report-only with verb Check, `dedup --suggest-only`).

## Deviations from plan

- Biome's partial Svelte support flagged `let label = $state(…)` in `Smoke.svelte` as unused
  (it cannot see template usage) and wanted to reformat the component — `.svelte` files are now
  excluded from Biome (`!**/*.svelte`); `svelte-check` is the component gate. The S01-T05
  verification had not run `npm run lint`, which is why this surfaced only now.
- Catalogue argv for `links`/`dedup` changed (+ `test_actions.py`, `test_menu_context.py`).

## Follow-ups

- T04 feeds real parser output into `mergeActions` and deletes `ADVANCED_COMMANDS`;
  `ENGINE_COMMANDS` in `vault/compile.ts` shrinks to `update` + `compile` once `runArgs` carries
  every other action.
- KNOWLEDGE: Biome bullet updated (Svelte files excluded; svelte-check owns them).

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint` — passed (typecheck + svelte-check
0 errors, vitest 61 passed / 1 skipped incl. 8 new cases, biome 0 errors / 9 warnings in
doomed files). Python: `test_actions` + `test_menu_context` 30 passed. TDD: `actions.test.ts`
failed on the missing module before the implementation.
