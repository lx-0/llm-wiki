---
milestone: M033
slice: S04
task: T03
project: llm-wiki
closed: 2026-10-15T11:24:00+02:00
verification: passed
---

# M033-S04-T03 -- Summary

## Commits

`98603a2` — the split. Planning commit `28dba21`. This summary, the slice-plan flip and
STATE follow under the same ref (`git log --grep '^M033-S04-T03'`).

## Outcome

The compile path reads as its stages. `compile.main` (345 → 60 lines) orchestrates
setup → parser → lock → clippings sweep → selection → dry-run → batch → final stamp →
corpus passes → summary → maintenance over `_build_parser`, `_sweep_clippings`,
`_compile_batch` (the per-file loop with the exception demotion, the skipped / failed /
compiled branches and the per-file persist; `_abort_reason` owns the four
consecutive-failure classifications), `_run_corpus_passes` (backlinks, relativize, index
sync) and `_log_run_summary` (the history event + the summary lines) with `_BatchStats` as
the loop's result. `_run_compile_route` (164 → 18) is `_log_dispatch_decision` →
`_memory_prepass` → `_compile_aggregated` (chunk loop + circuit breaker) or
`_outcome_from_result`. `compile_stages.compile_source` (212 → 56) is
`_render_compile_prompt` → budget check → `_warn_fragile_size` → `_attempt` →
`_retry_long_context` (the one-shot kind=unknown ladder) → `_skip_for_structural_failure`
(timeout / max_turns / long-context and small-source kind=unknown) → result. A pure move:
the same log lines at the same levels, the same `CompileOutcome` / `CompileResult` fields
on every path, the same write order; the tests' module-global patches (`compile_mod.*`,
`cs_mod.query` / `render`) still bind.

Evidence: the string-literal diff between HEAD and the tree is variable renames, two
adjacent string halves the formatter joined, and the new docstrings (none at all in
`compile_stages/compile.py`); the ten compile suites + state-store + the gate + the oracle
(125 tests) and the full suite (2119) are green; no function in the two modules is ≥ 150
lines (`_attempt` 118 and `_compile_batch` 99 are the longest). End to end on the scratch
vault (operator config, `claude-opus-4-8`, maintenance drain off): three fixture notes
compiled on the pre-split engine (`28dba21`, 42 s, $0.08) and again on `98603a2` (62 s,
$0.11) — `state.json` carries the three hashes both times, and the normalized logs (27
lines: the candidate list, the per-file ✓ and post-pass lines, the `--max-files` stop,
the two passes, the summary, the maintenance note) differ only in the per-file token
counts the agent's tool use produces.

## Deviations from plan

- The "E2E on three files" needed the scratch config's `piggybacks_on_compile` switched
  off so the two runs stay comparable and do not spawn the maintenance drain (dream /
  lint / curiosity) on the scratch; recorded in the slice notes. The three fixture notes
  produced no `knowledge/` articles in either run (the agent wrote nothing for the
  trivial notes) — the comparison is the batch loop, the persist and the summary, which
  is what the move touched.
- `_memory_prepass` returns the metadata (unchanged or replaced) instead of rebinding a
  local; `_compile_batch` carries the counters in `_BatchStats` — the same numbers, one
  value instead of nine locals.

## Follow-ups

- None for the compile path. The longest remaining functions here (`_attempt` 118,
  `_compile_batch` 99) are under the gate.

## Verification

Plan command 1 → targeted set `125 passed`; `uv run pytest -q` → **2119 passed, 1
skipped**; `ruff check` → `All checks passed!`; `ruff format --check` → clean (compile.py
formatted by explicit path). Plan command 2 → `0`. Plan command 3 (`/tmp/t03-e2e.sh
before` on `28dba21`, `after` on `98603a2`) → both `3 done · 0 failed · 0 skipped · 2
pending of 5`, three hashes in `state.json`, normalized log diff = token counts only. CI:
`28dba21` green; `98603a2` recorded in STATE.
