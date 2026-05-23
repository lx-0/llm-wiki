---
milestone: M026
slice: S02
task: T01
project: llm-wiki
closed: 2026-05-23T14:45:00+0200
verification: passed
---

# M026-S02-T01 -- Summary

## Outcome

`compile_stages/route.py` now owns the pure routing decision. The dispatch tables
(`SUBSTRATE_PROMPTS`, `_DEFAULT_DISPATCH`, `_SUBSTRATE_PATH_FALLBACKS`) and the
frontmatter/stub helpers (`_substrate_key`, `_frontmatter_type/_compile_role/_field`,
`_parse_frontmatter`, `_health_rollup_body_is_stub`) moved here from `compile.py`,
which now re-imports them — so `compile_file`'s still-inline logic and the
`from compile import _frontmatter_*` test imports are unchanged. `decide_route(source,
content, *, force) -> Route` reproduces `compile_file`'s pre-LLM decision in order
(empty→Skip, final-only→Skip, source-and-final→IndexOnly, skip-list→Skip,
health-stub→HealthStub, else→Compile with dispatch metadata + ClassifyResult), pure:
no logging, no I/O, no state. **Nothing calls `decide_route` yet** (wiring is T02), so
engine behavior is provably unchanged — confirmed by the existing compile suite staying
green after the move.

## Deviations from plan

- none material. The plan's file set held (route.py, compile.py, test_decide_route.py).

## Follow-ups

- **Dead branch surfaced (out-of-scope to fix here):** the model size-escalation +
  force-long-context branches in the precedence ladder are currently unreachable for
  real data — every `SUBSTRATE_PROMPTS` entry and `_DEFAULT_DISPATCH` pin
  `claude-haiku-4-5-20251001`, so `substrate_model` is always truthy and "substrate_model
  wins" short-circuits escalation. Ported faithfully (no behavior change) and covered by
  a patched-dispatch test. Worth a separate decision later: is haiku-everywhere intended,
  or should some dispatch entries use `model=None` to re-enable size-escalation? Logged
  here, not acted on.

## Verification

Command: `pytest tests/test_decide_route.py …` (+ full compile suite) — passed. 11 new
decide_route table-tests; 100 compile-suite tests green; `import compile` clean with
re-exports intact. Committed `2c4335c`.
