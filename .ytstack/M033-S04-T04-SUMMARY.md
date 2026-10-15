---
milestone: M033
slice: S04
task: T04
project: llm-wiki
closed: 2026-10-15T11:29:00+02:00
verification: passed
---

# M033-S04-T04 -- Summary

## Commits

`0ec0dda` — the split. Planning commit `a20eee2`. This summary, the slice-plan flip and
STATE follow under the same ref (`git log --grep '^M033-S04-T04'`).

## Outcome

`run_sdk_query` (339 lines → 41) reads as its mechanics list behind the same signature:
sanitize the env → `_build_options` (the `ClaudeAgentOptions` assembly with the three
write-gating shapes and the host-MCP isolation) → the stream (`_StreamState` +
`_consume_stream`, the one message loop with the per-message stall timeout) → one of three
endings — `_timeout_result` (warn, best-effort `aclose`, diagnose, partial result),
`_failed_stream_result` (the structured `ResultMessage(is_error)` classified from the
payload with the authoritative usage, else the crash diagnosed by `log_sdk_failure`),
`_clean_end_result` — each recording the cache-inclusive totals through `_record_usage`
and building the `SdkRunResult` from the same accumulated state. The late imports stay
late inside the helpers that use them, so `sdk_helpers` is as import-light as before and
the tests' call-time patches (`core.usage.LEDGER`, the SDK symbols, `CONFIG.features`)
still bind. A pure move: the same options kwargs, the same log lines, the same result
fields on every path. Evidence: the string-literal diff between HEAD and the tree is two
f-string variable renames and the dataclass docstring; the harness suites + the compile
reliability suite + the gate are green (101), the full suite is 2119; the live
single-call probe (`/tmp/t04-probe.py`, Haiku, one turn, no tools, no ledger write)
returns the identical five-line shape before (`c6b3dbd`) and after (`0ec0dda`): `OK`,
no failure, `num_turns 1`, `subtype success`, tokens and cost > 0. `sdk_helpers.py` has no
function ≥ 150 lines (`make_path_scope_hook` 95 is the longest); the allowlist is at 14.

## Deviations from plan

- `agen` is initialised to `None` before the stream so the timeout ending's best-effort
  `aclose` cannot hit an unbound name if `query_fn` itself stalls — the only line that is
  not a verbatim move.
- The `claude_agent_sdk.query` import now happens only when no `query_fn` is passed (the
  tests always pass one); the SDK classes are imported where they are used.

## Follow-ups

- None. `_build_options` (82) and `_failed_stream_result` (77) are well under the gate.

## Verification

Plan command 1 → targeted set `101 passed`; `uv run pytest -q` → **2119 passed, 1
skipped**; `ruff check` → `All checks passed!`; `ruff format --check` → clean
(sdk_helpers.py formatted by explicit path). Plan command 2 → `0`. Plan command 3 → the
probe's five lines identical before/after (`PROBE SHAPE IDENTICAL`). CI: `a20eee2` +
`c6b3dbd` green; `0ec0dda` recorded in STATE.
