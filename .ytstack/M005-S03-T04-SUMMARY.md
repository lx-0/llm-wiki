---
milestone: M005
slice: S03
task: T04
project: llm-wiki
closed: 2026-05-15T19:20:00Z
verification: passed
---

# M005-S03-T04 -- Summary

## Commits so far (auto-tracked by post-tool-use-bash hook)

- `11b96f6` -- audit(compile): routing infra already supports commitment extraction (M005-S03-T03) — **NOT T04 work.** The hook recorded this T03-closing commit under T04 because STATE.md was advanced to active_task: T04 in the same operation. Triple-recorded by the hook firing on each bash invocation in that turn.

(T04 work landed in the commit that closes this task — see below.)

## Outcome

Three artifacts shipped under `tests/fixtures/jamie/`:

- `2026-04-15--canary-q1-review--abc.md` — synthetic jamie transcript imitating live shape (frontmatter + `## Summary` + `## Transcript` with speaker labels). Contains 3 real commitments + 1 rejected hypothetical + 1 closing pleasantry, plus an `## Expected extraction` block that is canary truth-set for T05 (the LLM ignores it during compile since it's clearly meta-doc, not transcript content).
- `README.md` — contract doc explaining the fixture convention.

`tests/test_jamie_extraction_fixture.py` — three test cases:

- `test_fixture_exists_with_jamie_naming_convention` — asserts the filename matches `<date>--<slug>--<short-id>.md`.
- `test_fixture_carries_canonical_commitment_markers` — asserts the body contains the three commitment signals + the hypothetical control.
- `test_rendered_prompt_carries_substrate_and_extraction_rule` — renders the compile prompt with the fixture as `source_content` + jamie substrate-path, asserts (a) extraction rule headline reaches the prompt, (b) substrate body is interpolated unchanged, (c) the substrate-path is interpolated into the prompt.

Full suite: 233 passed (230 prior + 3 new).

## Deviations from plan

None.

## Follow-ups

- T05 real-substrate canary: pick one live jamie file from lxw vault, run compile against it (or against this synthetic fixture as a smaller starting point), spot-check whether the LLM emits a `knowledge/people/jane-doe.md` two-layer page with the three commitments correctly routed. Operator-iteration loop on the prompt if quality is weak.

## Verification

```
test -f tests/fixtures/jamie/2026-04-15--canary-q1-review--abc.md && \
test -f tests/fixtures/jamie/README.md && echo OK
# → OK

uv run --project . pytest -q tests/test_jamie_extraction_fixture.py
# → 3 passed in 0.01s

uv run --project . pytest -q tests/
# → 233 passed in 0.50s (+3 from prior 230)
```

Result: **passed**.
