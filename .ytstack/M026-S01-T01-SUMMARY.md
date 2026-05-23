---
milestone: M026
slice: S01
task: T01
project: llm-wiki
closed: 2026-05-23T14:09:59+0200
verification: passed
---

# M026-S01-T01 -- Summary

## Outcome

The compile pipeline now has the two types the dispatch-seam refactor returns.
`compile_stages/types.py` gained `CompileOutcome` — a frozen dataclass (`status` ∈
compiled/skipped/failed, plus `skip_reason`, string `failure_kind`/`failure_detail`,
`ingest_hash`, cost/token fields) that will replace `compile_file`'s magic-key return
dict. `compile_stages/route.py` (new) holds the `Route` union — frozen `Skip(reason)`,
`IndexOnly(title, wikilinks)`, `HealthStub()`, `Compile(metadata, classification)` —
where `Compile` carries a `CompileMetadata` + the existing `ClassifyResult`. Both are
exported from `compile_stages/__init__.py`. `route.py` imports `.types` and `.classify`;
neither imports `route`, so `decide_route` (S02) can stay pure with no import cycle.
CONTEXT.md's `CompileOutcome` block was aligned to the shipped string-based
`failure_kind`/`failure_detail` shape. Purely additive — no production code calls the
new types yet, so engine behavior is unchanged.

## Deviations from plan

- Plan sketched `failure: FailureClass | None`; shipped string `failure_kind`/
  `failure_detail` (matches `CompileResult`, keeps `types.py` free of a
  `core.sdk_helpers` import). CONTEXT.md updated to match — was in the plan's Files.
- `route.py` created here (S01) rather than left as an S02 "scaffold" — natural home
  for `Route`, avoids a types.py→classify cycle.

## Follow-ups

- none net-new. S02 (decide_route) + S03/S04 already in
  `.ytstack/backlog/compile-dispatch-seam.md` + `M026-ROADMAP.md`.

## Verification

Command: `uv run --project .wiki pytest tests/test_compile_route_types.py
tests/test_compile_stages_types.py …` (+ broader compile suite) — passed. 9 new tests
+ 83 compile-suite tests green; `python -c "import compile_stages.route"` confirms no
cycle. Committed `4647d47`.
