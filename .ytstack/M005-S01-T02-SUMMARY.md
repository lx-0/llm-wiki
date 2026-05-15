---
milestone: M005
slice: S01
task: T02
project: llm-wiki
closed: 2026-05-15T17:45:00Z
verification: passed
---

# M005-S01-T02 -- Summary

## Outcome

`templates/AGENTS.example.md` now describes the two-layer shape for both `### People Articles` and `### Project Articles` sections. Each example block shows the full two-layer page: frontmatter with `type: person|project` + `compiled_from:` list, executive-summary blockquote, `## State` with structured fields, `## Action Items` in Obsidian-Tasks-plugin syntax (`- [ ]` + `📅` + `⏫`), `## Open Threads` as prose bullets, free-prose body section (`## What they're building` for people, `## What it is` + `## Key Decisions` for projects), `## See also`, then the `---` separator, then `## Timeline` (append-only reverse-chronological). A short "Rules" callout points back to `prompts/compile_main.md` Instruction 3 as the canonical contract — schema doc + compile prompt now agree on the shape.

## Deviations from plan

None. Task scope held: only `templates/AGENTS.example.md` touched. No new per-vault page templates under `templates/knowledge/people/` or `templates/knowledge/projects/` — would have added seed-confusion and the schema doc is the canonical reference.

## Follow-ups

- T03 (canary migration) can now copy from these examples when picking which existing `knowledge/people/<slug>.md` to rewrite.
- S02 lint check `check_two_layer_pages` will assert this exact shape on real entity pages.

## Verification

Commands run:

```
grep -cE '^### (People|Project) Articles' templates/AGENTS.example.md
# → 2

grep -cE '## (State|Action Items|Open Threads|Timeline)' templates/AGENTS.example.md
# → 11 (4 sections per example × 2 entity types + rule references)

diff <(grep -oE '## (State|Action Items|Open Threads|Timeline)' prompts/compile_main.md | sort -u) \
     <(grep -oE '## (State|Action Items|Open Threads|Timeline)' templates/AGENTS.example.md | sort -u)
# → empty diff (both files mention the same four section names)

uv run --project . pytest -q tests/
# → 218 passed in 0.51s
```

Result: **passed**.
