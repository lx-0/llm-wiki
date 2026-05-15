---
milestone: M005
slice: S02
task: T01
project: llm-wiki
closed: 2026-05-15T18:15:00Z
verification: passed
---

# M005-S02-T01 -- Summary

## Outcome

`scripts/lint.py:check_two_layer_pages()` shipped. The function iterates `knowledge/people/*.md` and `knowledge/projects/*.md`, filters to articles whose frontmatter `type:` matches the folder (avoiding double-reporting with `check_article_type`), strips the frontmatter so checks operate on the body, then asserts:

- `## State` heading present → else `error: two_layer_missing_state`
- A body-level `---` separator line appears *before* the `## Timeline` heading → else `error: two_layer_missing_body_separator`
- `## Timeline` heading present → else `error: two_layer_missing_timeline`
- Timeline entries starting with `- **YYYY-MM-DD**` are reverse-chronological — first chronology violation surfaces `warning: timeline_not_reverse_chronological` (one per file)
- If `## Action Items` exists: non-empty lines start with `- [ ]` / `- [x]` / `- [X]`. First malformed line surfaces `warning: action_items_malformed` (one per file). Full Obsidian-Tasks-syntax validation is T02's job.

Registered in the `checks` tuple in `main()` between "Concept domain tag" and "Sparse articles", so `wiki lint --structural-only` and the full `wiki lint` both run it.

## Deviations from plan

None. Plan held.

## Follow-ups

- T02 will deepen the Action-Items syntax check beyond the bare `- [ ]/[x]` prefix (📅 due-date format, ⏫ priority placement, 🔁 recurrence format).
- T03 will add broken-case test fixtures and a pytest that drives both T01 and T02 functions on them.

## Verification

```
grep -n "def check_two_layer_pages" scripts/lint.py
# → 362:def check_two_layer_pages() -> list[dict]:
grep -n '"Two-layer pages"' scripts/lint.py
# → 667:        ("Two-layer pages", check_two_layer_pages),

uv run --project . python scripts/lint.py --structural-only
# → "Checking: Two-layer pages..." / "Found 0 issue(s)" (engine repo has empty knowledge/)

uv run --project . pytest -q tests/
# → 220 passed in 0.41s (unchanged from prior — T02 will add tests)
```

Result: **passed**.
