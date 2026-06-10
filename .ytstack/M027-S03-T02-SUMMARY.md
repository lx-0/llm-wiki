---
milestone: M027
slice: S03
task: T02
project: llm-wiki
closed: 2026-06-10T18:50:00+0200
verification: passed
---

# M027-S03-T02 -- Summary

## Commits

- `aff144a` -- feat(M027-S03-T02): compile_curiosity_folder prompt template
- `f17236c` -- plan(M027-S03-T02): compile_curiosity_folder prompt template

## Outcome

`prompts/compile_curiosity_folder.md` exists and renders with exactly the
T01 producer kwargs (`source_path` / `source_content` / `folder_digests` /
`timestamp`). Sibling of `compile_curiosity.md`, adapted to the folder
pass: metadata-only honesty clause (the model has seen NO content — judge
by path/name/dates/size only), verbatim-path contract with the server-side
file-exists anchor spelled out ("gaps naming an unlisted path are dropped,
no exceptions"), JSON contract matching the T01 schema (topic / root_id /
file_path / file_confidence / rationale), folder-adapted 1-5 confidence
scale (5 = filename names the topic exactly), created-date sync caveat as
an explicit rule, abstention-preferred ("empty array is VALID and
PREFERRED"). Render-smoke test pins the contract: digest block embedded,
all field names present, no unsubstituted `${`.

## Deviations from plan

None — plan held (1 template + 1 test).

## Follow-ups

- Prompt QUALITY against the real local LLM (llama3.1:8b precision on
  verbatim paths / abstention) is deliberately unverified — measurable
  only after T03 wires the producer into the compile pass and lxw runs
  real sources. Expect a tuning loop then (M027-CONTEXT Q7 anticipated
  lower precision than email).
- T03 next: `producers/folder_curiosity.py` registration +
  `producers/__init__.py` import + `_dispatch` branch in
  `curiosity/cli.py`.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py -q` then
`uv run pytest -q` -- passed. Full suite **1238 passed, 0 failed**.
