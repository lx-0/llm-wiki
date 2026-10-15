---
milestone: M033
slice: S05
task: T04
project: llm-wiki
closed: 2026-10-15T15:54:43+02:00
verification: passed
---

# M033-S05-T04 -- Summary

## Commits

- `ba73be9` -- planned
- `e2f9c3b` -- the desktop validates against the same contract

This summary, the slice-plan flip and STATE follow under the same ref.

## Outcome

Engine and desktop validate against the same two schema files. pytest uses `jsonschema`
(T03), and vitest uses `ajv` 8.20, a dev dependency. `desktop/src/lib/contract.ts` is test
support that the app never imports. It compiles `docs/contracts/{menu,doctor}.schema.json` and
exports `validateMenu` / `validateDoctor` and a `fieldInventoryDrift` check.

`desktop/src/lib/contract.test.ts` (6 cases) checks that:

- the schema `const` equals `ACTION_SCHEMA`;
- the engine's oracle goldens validate under ajv, and run through `parseMenu` /
  `parseDoctor` with no suggestion, tool or actionable check dropped;
- an unknown key and a wrong type are rejected;
- the field inventory (`StatusJSON`, `SuggestionJSON`, `ActionJSON`, `CheckJSON` against the
  fields the app knows) is clean, and reports `badge` on a schema copy grown by that field.

The representative fixtures validate too. `menu.test.ts`'s payload passed as it was.
`doctor.test.ts`'s became a full envelope (`vault`, `engine_revision`, `summary`), with every
check carrying every key and `null` where the engine sends `null`. Its assertions are
unchanged. The fallback fixtures in both files stay partial on purpose, and a comment says so.

Open question 2 is decided and recorded in DECISIONS 2026-10-15. The payloads are typed as
`TypedDict`s and turned into JSON Schemas. The desktop keeps its hand-written TS types, guarded
by the inventory test, because the schemas are small (seven object types) and the app's types
are normalised views. Open question 1, decided in T01, is struck in CONTEXT too.

## Deviations from plan

- **The lockfile also corrects its stale root name** (`desktop` became `llm-wiki-desktop`, the
  name in `package.json`). npm made that change on install; ajv and its four dependencies are
  the only packages added.
- **Open question 1 struck here.** It was decided in T01, but CONTEXT still listed it open.

## Follow-ups

- None for the contract. A new payload field now fails three places until it is handled: the
  engine's golden validation, the schema `--check`, and the desktop's inventory test.
- T05 (closeout docs) re-reads `desktop/README.md` with the rest. It already names the contract
  tests.

## Verification

`cd desktop && npm test` runs tsc, svelte-check and vitest: 21 files passed (2 skipped),
**120 tests passed** (112 before, 8 new). `npm run lint` reports biome checked 79 files, no
issues. The engine suite reports 2255 passed. The negative cases fail as they should: an
unknown key, a wrong type, and a grown schema reported by the inventory.

CI is green on `e2f9c3b`. The engine job (ruff + ty + pytest) and the desktop job
(typecheck + vitest + biome) both succeeded on Linux, reading `docs/contracts/` and
`tests/golden/` from the checkout.
