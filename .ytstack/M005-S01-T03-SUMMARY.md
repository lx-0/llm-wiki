---
milestone: M005
slice: S01
task: T03
project: llm-wiki
closed: 2026-05-15T17:55:00Z
verification: passed
---

# M005-S01-T03 -- Summary

## Commits so far (auto-tracked by post-tool-use-bash hook)

- `80119a1` -- fix(curiosity): soften quote-gate to N-token anchor — paraphrase tolerance (2026-05-15T15:18:27Z) — **NOT T03 work.** Parallel session committed this while STATE.md had `active_task: T03`; the auto-draft hook recorded it under T03 incorrectly. The curiosity-quote-gate change is its own arc, unrelated to M005-S01-T03 fixtures.
- (T03 fixtures landed in the commit below this section.)

## Outcome

Two canonical two-layer-shape fixtures live in `tests/fixtures/two_layer/`:

- `person_jane-doe.md` — `type: person` page demonstrating the full shape: executive-summary blockquote, `## State` with structured fields, `## Action Items` (2 entries with `📅` due dates and one `⏫` priority), `## Open Threads` (2 prose bullets), `## What they're building` body with wikilinks, `## See also` with three cross-references, `---`, then `## Timeline` (3 reverse-chronological entries citing jamie / daily / daily sources).
- `project_yesterday-platform.md` — `type: project` page with the same shape, project-relevant State fields (Status, Stack, Owner, Deployment), 3 Action Items, 2 Open Threads, `## What it is` + `## Key Decisions` body sections, cross-link to `[[knowledge/people/jane-doe]]`, and a 3-entry Timeline.
- `README.md` — one-paragraph contract: S02's `check_two_layer_pages` MUST pass on every file in this directory; lint failures here mean either the lint is wrong or the spec drifted.

The two fixtures cross-link via `[[knowledge/people/jane-doe]]` / `[[knowledge/projects/yesterday-platform]]` — they double-purpose as cross-link test material for future lint work.

## Deviations from plan

Two:

1. **Decision-level (planned in the AskUserQuestion phase, not after):** the original slice-plan wording said "Hand-migrate one existing `knowledge/people/<slug>.md`". Engine-repo has no `knowledge/people/`; real pages live in the lxw vault. Picked test-fixtures (engine-repo-local, testable, no engine↔vault boundary breach) over vault migration. Real-world canary in lxw is deferred until S03 (substrate extraction) ships and `wiki update` lands the new schema — tracked as follow-up below.

2. **Auto-draft drift:** the `post-tool-use-bash` hook attributed the parallel-session curiosity-fix commit `80119a1` to T03 because STATE.md had `active_task: T03` when it landed. Noted in the commits section above; not corrected at the hook level (out of scope for T03).

## Follow-ups

- After S03 ships and lxw runs `wiki update`: one productive person-page in lxw should be hand-migrated to validate the schema works on real-world substrate, not just synthetic fixtures. Backlog candidate `m005-lxw-canary-migration.md` if not done inside S03.
- S02 `check_two_layer_pages` will consume these fixtures as valid-case inputs; will also need a broken-case fixture (e.g. `tests/fixtures/two_layer_broken/` or inline string fixtures in the test file).
- Possible hook bug: `post-tool-use-bash` auto-draft attribution should filter commits whose subject is clearly unrelated to `active_task`. Low priority — minor noise in summaries.

## Verification

```
test -f tests/fixtures/two_layer/{person_jane-doe,project_yesterday-platform,README}.md
# → OK

grep -cE '^## (State|Action Items|Open Threads|Timeline)' tests/fixtures/two_layer/person_jane-doe.md
# → 4
grep -cE '^## (State|Action Items|Open Threads|Timeline)' tests/fixtures/two_layer/project_yesterday-platform.md
# → 4

grep -c '^---$' tests/fixtures/two_layer/person_jane-doe.md
# → 3 (two frontmatter delimiters + one body separator)
grep -c '^---$' tests/fixtures/two_layer/project_yesterday-platform.md
# → 3

uv run --project . pytest -q tests/
# → 218 passed in 0.48s
```

Result: **passed**.
