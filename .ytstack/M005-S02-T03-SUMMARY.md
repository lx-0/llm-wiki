---
milestone: M005
slice: S02
task: T03
project: llm-wiki
closed: 2026-05-15T18:35:00Z
verification: passed
---

# M005-S02-T03 -- Summary

## Outcome

S02 closed end-to-end. Six broken-case fixtures under `tests/fixtures/two_layer_broken/`, each violating one schema rule:

- `missing_state.md` — no `## State` heading
- `missing_separator.md` — no body-level `---` between State and Timeline
- `missing_timeline.md` — no `## Timeline` heading (`type: project`)
- `timeline_out_of_order.md` — Timeline ascending instead of newest-first
- `malformed_action_items.md` — three concurrent malformed-syntax cases (📅 without date, ⏫ glued to text, 🔁 empty)
- `action_item_no_checkbox.md` — Action Items line without `- [ ]` prefix
- `README.md` — contract doc for the directory

`tests/test_two_layer_lint.py` (8 test cases):

- 2 cases drive both `check_two_layer_pages` and `check_action_item_syntax` on the **valid** fixtures (`tests/fixtures/two_layer/`) and assert ZERO issues — protects the contract from S01-T03.
- 6 cases drive a single broken fixture through the relevant check and assert the expected `check` issue-code appears. Uses a `with_knowledge` pytest fixture that builds a fake `knowledge/` tree in `tmp_path`, files each fixture under `people/` or `projects/` based on `type:`, and monkeypatches `lint.KNOWLEDGE_DIR` for the duration.

Full suite: 228 passed (220 prior + 8 new).

## Deviations from plan

One scope clarification: the original slice-plan wording mentioned "wire both checks into `wiki lint` CLI + `health.py`". CLI-wiring was already done in T01/T02 (functions registered in `main()`'s `checks` tuple). `health.py` is a dashboard renderer, not a lint runner — the slice-plan reference was a miswording. T03 dropped the health.py mention; flagged in plan.

## Follow-ups

- S03's substrate-extraction work will produce real entity pages — `wiki lint` will start surfacing real-world issues from these checks once those pages exist in lxw.
- If future Obsidian-Tasks-plugin metadata grows (e.g. `🛫 start date`, `✅ done date`), `check_action_item_syntax` gets a parallel rule added; the pattern is established.

## Verification

```
ls tests/fixtures/two_layer_broken/*.md | wc -l
# → 7 (6 broken + README)

uv run --project . pytest -q tests/test_two_layer_lint.py
# → 8 passed in 0.28s

uv run --project . pytest -q tests/
# → 228 passed in 0.43s (+8 from prior 220)
```

Result: **passed**. S02 closed.
