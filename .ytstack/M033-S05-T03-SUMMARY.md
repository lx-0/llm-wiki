---
milestone: M033
slice: S05
task: T03
project: llm-wiki
closed: 2026-10-15T15:45:51+02:00
verification: passed
---

# M033-S05-T03 -- Summary

## Commits

- `1070585` -- planned
- `3f153d2` -- the schema-2 contracts typed once (module, schemas, tests, builders, docs)

This summary, the slice-plan flip and STATE follow under the same ref.

## Outcome

`scripts/core/contracts.py` defines every schema-2 `--json` payload once, as `TypedDict`s:

- `ActionJSON` and `CheckJSON`, moved in from `core/actions` / `core/health`
- `SuggestionJSON(ActionJSON)`
- `StatusJSON` (`total=False`)
- `MenuJSON`
- `HealthSummaryJSON`
- `DoctorJSON`

The module also holds a small TypedDict → JSON Schema (draft 2020-12) converter.
`python -m core.contracts --write` generates `docs/contracts/menu.schema.json` and
`docs/contracts/doctor.schema.json`, and `--check` is the drift gate. Every object is
`additionalProperties: false`, so a key the engine emits without the types fails validation
instead of drifting past a consumer.

The builders now return the types:

- `core.actions.ActionSpec.to_json` / `tools`
- `core.health.to_json` / `health_summary`
- `menu_context.build_status` / `build_suggestions` and the emitted envelope
- `doctor.render_json` / `render_pretty`
- `menu.py`'s `HomeState`

The report-only ty count for all of `scripts/` stays 148, with the same findings line by line.

`tests/test_contracts.py` (10 cases) checks that the schemas are current and that both oracle
goldens (the engine's real output on the fixture vault) validate. It also checks that an
unknown key, a wrong type, a missing key and a fifth severity are rejected, and that the
status keys are optional. The live payloads on the scratch vault validate on the old engine
(`2bacfc2`: 4 suggestions, 5 tools, 20 checks) and on the new one (`3f153d2`).

## Deviations from plan

- **Two files outside the plan's list.** `menu.py`'s `HomeState` and the `render_pretty`
  signature were typed too, to keep the report-only count from growing: the plan's
  "must not grow" first measured 152, then 150. The finding set now diffs empty against T02's
  148.
- **`menu_context.build_suggestions` builds each entry with `"key": ""`.** The key is
  numbered after the sort, exactly as before. The placeholder holds the key's position, so the
  emitted JSON (key order, values) is unchanged, as the oracle golden proves.
- **`StatusJSON` is `total=False`, not `NotRequired[...]`.** Measured: under
  `from __future__ import annotations`, Python 3.12's TypedDict lists a string
  `NotRequired[int]` as required, which would have made the generated schema demand all three
  status keys. The measurement is in KNOWLEDGE.
- **`health_summary` returns `HealthSummaryJSON` through a `cast`.** It keeps counting
  whatever severity a check reports. A severity outside the four would add a key the contract
  rejects, and a test pins that rejection.
- **The plan's "docs/contracts/actions.schema.json" became one file per payload** (`menu`,
  `doctor`), which is what T04's fixtures validate against.
- **`docs/cli.md` corrected a prose detail.** It listed `fix?` / `dispatch_args?` / `details?`
  as optional; they are always present and nullable, and the schema says so.

## Follow-ups

- **T04 (desktop).** `scripts/shots/fixtures.cjs` and `src/vault/*.test.ts` validate against
  `docs/contracts/*.schema.json` with ajv. Then decide generated vs hand-written TS types by
  schema size: two documents, seven object types, the largest with nine properties.
- **`group` and `severity` stay `str` in the contract.** The desktop's TS narrows them to
  unions. Typing them as `Literal`s in `core/` would turn ActionSpec / CheckResult strings
  into literals; that is a candidate if T04 shows the desktop needs it.

## Verification

Plan command 1: `python -m core.contracts --check` exits 0. `tests/test_contracts.py` and the
oracle tests pass. `ty check scripts/core` reports `All checks passed!`. The full suite reports
**2255 passed, 1 skipped**, and `ruff check` is clean.

Plan command 2: `/tmp/t03-contracts-e2e.sh --update` on the scratch vault, engine `3f153d2`,
reports `menu: valid`, `doctor: valid`. The same run on `2bacfc2` before the commit was valid
too.

CI is green on `3f153d2` (ci + secrets-scan).
