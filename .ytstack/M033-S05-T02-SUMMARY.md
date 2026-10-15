---
milestone: M033
slice: S05
task: T02
project: llm-wiki
closed: 2026-10-15T15:34:23+02:00
verification: passed
---

# M033-S05-T02 -- Summary

## Commits

- `c51e52d` -- planned (two commits: `core/` green, then the gate)
- `dae1395` -- (A) `scripts/core/` green under ty, plus the payload `TypedDict`s
- `ead5379` -- (B) the gate: pre-commit hook, CI gating step + report-only step, AGENTS,
  KNOWLEDGE

This summary, the slice-plan flip and STATE follow under the same ref.

## Outcome

`ty check scripts/core` passes (`All checks passed!`), where it exited 1 with 19 diagnostics
before A. It runs as a local pre-commit hook on changes under `scripts/core/` or to
`pyproject.toml` / `uv.lock`, and as a gating CI step. A second CI step reports all of
`scripts/` without failing the build; its first run printed `Found 148 diagnostics`, the
same count as on the Mac.

The 19 diagnostics had five roots, each fixed where it was:

- **`sdk_helpers` (13).** The options, the prompt and the stream's final message were typed
  `object`, and now carry the SDK types (`ClaudeAgentOptions`, `str | AsyncIterable[...]`,
  `ResultMessage | None`). The SDK types are imported under `TYPE_CHECKING`; the late runtime
  imports stay. The env helper takes a `MutableMapping[str, str]`, so its mypy-coded
  `type: ignore[arg-type]` is gone.
- **`config_docs` (4).** `dataclasses.fields` wants `type[DataclassInstance]`, and the
  section table plus its two readers now say so.
- **`piggyback_runner` (1).** The handler table carries `signal`'s handler type instead of
  `object`.
- **`health` (1).** A `Callable` promises no `__name__`. The probe-failed label reads it
  through `getattr`, which gives identical output for the functions in `_ALL_CHECKS`.

The two dict payloads the desktop reads are typed once. `core.actions.ActionJSON` covers
`ActionSpec.to_json` and `tools()`. `core.health.CheckJSON` covers `to_json`, as a `cast`
over `asdict` that keeps the field order and the deep copies. T03 builds the JSON Schema from
these two.

There is no behaviour change. The oracle goldens (`doctor --quick --json`, `menu --json`) are
identical, and the suite passes with 2245.

## Deviations from plan

- **The gate was shown failing through the hook as well.** An `int = "str"` assignment was
  injected into `core/errors.py`; the hook went `Failed` with `invalid-assignment`, then
  `Passed` once the line was reverted by edit and the file was back to HEAD.
- **`health.to_json` keeps `asdict` behind a `cast`.** The alternative was building the
  `TypedDict` field by field, which would have dropped `asdict`'s deep copy and risked the key
  order the golden pins. The `cast` asserts exactly what `asdict` returns, with `verb` set on
  the next line.
- **Pre-commit is not installed globally on the Mac.** The hook was verified through
  `uvx pre-commit run ty --all-files`.

## Follow-ups

- **T03.** Generate the JSON Schema from `ActionJSON` / `CheckJSON` plus the `menu --json`
  envelope that `menu_context.py` builds outside `core/`: actions with `count`, `label`,
  `priority` and `key` spread over `ActionJSON`.
- **Widening the gate.** KNOWLEDGE records the rule (a package goes to 0, then into both
  paths) and the starting point. `probe_compile_scope.py` (47) is an operator-run probe and
  `collectors/` (40) is the largest real package.
- **pyright-only findings, re-checked.** Neither appears in the gate. The module `__doc__` as
  `str | None` (`piggyback_runner.main`) and the hook callback's signature against the SDK's
  `HookCallback` stay unchanged, because ty does not report them and both are safe in
  practice: the module has a docstring, and the SDK calls the hook with the documented
  arguments.

## Verification

Plan command 1: `ty check scripts/core` reports `All checks passed!` (exit 0; exit 1 with 19
before A). `uv run pytest -q` reports **2245 passed, 1 skipped**. `ruff check` and
`ruff format --check` are clean.

Plan command 2: `uvx pre-commit run ty --all-files` reports `Passed` (`Failed` on the injected
error). CI on `ead5379` succeeded. Its engine job shows `ty check scripts/core` succeeding with
`All checks passed!`, and `ty check scripts (report only)` succeeding with
`Found 148 diagnostics`. CI on `dae1395` is green as well.
