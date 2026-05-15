---
milestone: M005
slice: S02
task: T02
project: llm-wiki
closed: 2026-05-15T18:25:00Z
verification: passed
---

# M005-S02-T02 -- Summary

## Outcome

`scripts/lint.py:check_action_item_syntax()` shipped. Scans `## Action Items` sections in `knowledge/people/*.md` and `knowledge/projects/*.md` (only when frontmatter `type:` matches the folder), validates Obsidian-Tasks-plugin syntax on each `- [ ]` / `- [x]` line:

- `📅 ` (date emoji + space) must be followed by `YYYY-MM-DD` → else `warning: action_item_invalid_due_date`
- `⏫` priority must be whitespace-bounded → else `warning: action_item_malformed_priority`
- `🔁 ` recurrence must be followed by non-empty content → else `warning: action_item_empty_recurrence`

One issue per file per rule (a file with three malformed due dates surfaces once). Registered in `main()` checks tuple between "Two-layer pages" and "Sparse articles".

## Deviations from plan

None. Implementation matches the plan; regex bounds match what the plan specified.

## Follow-ups

- T03 will validate both checks against deliberately broken fixtures (`tests/fixtures/two_layer_broken/`) — exercises the warning paths that today have no test coverage.

## Verification

```
grep -n "def check_action_item_syntax" scripts/lint.py
# → 460:def check_action_item_syntax() -> list[dict]:
grep -n '"Action item syntax"' scripts/lint.py
# → 741:        ("Action item syntax", check_action_item_syntax),

uv run --project . python scripts/lint.py --structural-only
# → "Checking: Two-layer pages..." / "Checking: Action item syntax..." both run cleanly

uv run --project . pytest -q tests/
# → 220 passed in 0.42s (T03 will add tests)
```

Result: **passed**.
