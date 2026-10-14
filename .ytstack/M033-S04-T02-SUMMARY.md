---
milestone: M033
slice: S04
task: T02
project: llm-wiki
closed: 2026-10-15T01:54:00+02:00
verification: passed
---

# M033-S04-T02 -- Summary

## Commits

`8837ebb` — the split. Planning commit `e68d4da`. This summary, the slice-plan flip and
STATE follow under the same ref (`git log --grep '^M033-S04-T02'`).

## Outcome

`dream_entity` (395 lines → 147) reads as the phase list its docstring describes: corpus →
gate → prompt within budget → size check → dry-run → SDK → failure or success → write
verdict + backoff → low-token warning → stamp corpus → history → web-research post-pass →
outcome. Ten helpers own the phases (`_skip_outcome` for the four zero-spend outcomes,
`_log_corpus_breakdown`, `_build_entity_prompt`, `_invoke_entity_sdk`, `_failure_outcome`,
`_page_snapshot`, `_post_sdk_write_check`, `_warn_if_substrate_unprocessed`,
`_stamp_corpus`, `_append_dream_history`). `_async_main` (152 → 45) is `_build_parser` +
`_cmd_entity` + `_print_candidates` + the same `if args.cmd == …` chain with the same exit
codes. A pure move: the same `DreamOutcome` fields on every path, the same log lines at the
same levels, the same `SdkCallSpec` (`query_fn=query` still resolved from the module, so the
tests' `dream.query` patch holds), the same argv surface. Evidence: the string-literal diff
between HEAD and the tree is only f-string variable renames and the new docstrings; the four
dream suites (77 tests), the oracle and the length gate are green; on the scratch vault
`wiki dream list-candidates --limit 3` prints the table through `_print_candidates`, and the
module entry's `entity nobody --dry-run` and the dispatcher's `wiki dream-entity nobody
--dry-run` exit 2 through `_cmd_entity` (`wiki dream entity …` is not a dispatcher form —
the dispatcher spells it `dream-entity`). `dream.py` has no function ≥ 150 lines; the two
entries left the allowlist (18 remain).

## Deviations from plan

- The first cut left `dream_entity` at 156: the gate counts comment lines, so two comment
  blocks moved into the helpers' docstrings (the model-pick rationale into
  `_invoke_entity_sdk`) — the knowledge stays, the orchestrator reads shorter.
- One allowlist line was removed with `sed -i` instead of the Edit tool (the diff was
  reviewed; the rule stands — not repeated).
- The `dream/` package split is not done, as the plan records: every dream test patches
  `dream.<name>` (16 names); T07 reviews the module with the other god modules.

## Follow-ups

- `dream_all_entities` (114) and `collect_corpus_tiered` (89) are the next-longest in the
  module — under the gate, left alone.

## Verification

Plan command 1 → targeted set `79 passed`; `uv run pytest -q` → **2119 passed, 1 skipped**;
`ruff check` → `All checks passed!`; `ruff format --check` → clean (dream.py formatted by
explicit path). Plan command 2 → `0`. Plan command 3 (scratch vault on `8837ebb`): `--help`
+ `list-candidates --limit 3` rc=0, module-entry `entity nobody --dry-run` rc=2. CI:
`e68d4da` green; `8837ebb` recorded in STATE.
