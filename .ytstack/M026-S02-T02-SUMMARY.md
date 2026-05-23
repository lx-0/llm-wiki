---
milestone: M026
slice: S02
task: T02
project: llm-wiki
closed: 2026-05-23T15:05:00+0200
verification: passed
---

# M026-S02-T02 -- Summary

## Outcome

`compile_file` is now a thin dispatcher: header log → dry-run early-return →
read-content → `route = decide_route(source, content, force=force)` → `isinstance`
dispatch on `Skip` / `IndexOnly` / `HealthStub` / `Compile`. Each arm runs the
existing execution code verbatim (per-reason skip log; index-write + state; health
stub record + state; Compile = dispatch log + memory pre-pass + chunk/single
`compile_source`). All routing decisions (compile_role, skip-list, dispatch
precedence, classify) now live in `decide_route` — `compile_file` only executes. The
memory pre-pass stays here (it writes a `## Timeline` section, I/O) and enriches
`route.metadata` via `dataclasses.replace`. `compile_file` still returns the legacy
magic-key dict (the typed `CompileOutcome` return is S04, where `main()` flips with it).

## Deviations from plan

- `tests/test_compile_reliability.py` fixture needed a `route_mod.ROOT_DIR` monkeypatch
  (the ROOT_DIR-dependent decision moved from `compile` into `compile_stages.route`).
  Standard per-module-monkeypatch fallout; not net-new scope.
- Dead escalation logs (`forcing [1m]` / `large source`) dropped — they never fire for
  real data (every dispatch entry pins haiku → substrate_model always wins). Functional
  no-op; logged as the same dead-branch follow-up from S02-T01.

## Follow-ups

- none net-new.

## Verification

Command: `pytest tests/test_compile_file_dispatch.py …` + full compile suite — passed.
4 characterization tests (written against the legacy body) pass before AND after the
refactor; 126 compile-suite tests green. 7 unrelated pre-existing failures
(dream_sampling time-drift + parallel email-config-key fixtures) untouched by M026.
Committed `aad8541`.
