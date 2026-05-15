# Two-layer entity-page fixtures

Introduced in M005-S01-T03. Canonical valid-case examples of the two-layer
State + Timeline shape defined by `prompts/compile_main.md` Instruction 3
and `templates/AGENTS.example.md`.

**Contract:** S02's `check_two_layer_pages` lint MUST pass on every file in
this directory (excluding this README). If it doesn't, either the lint is
wrong or the spec drifted -- both require a real fix, not a fixture edit.

**Files:**

- `person_jane-doe.md` -- canonical `type: person` page (executive summary,
  `## State`, `## Action Items` in Obsidian-Tasks syntax, `## Open Threads`,
  `## What they're building`, `## See also`, `---`, `## Timeline`).
- `project_yesterday-platform.md` -- canonical `type: project` page (same
  shape with project-relevant State fields, `## What it is`, `## Key Decisions`,
  cross-links to `jane-doe`).

The two cross-link via `[[knowledge/people/jane-doe]]` and
`[[knowledge/projects/yesterday-platform]]` so they also double-purpose as
cross-link test material for future lint work.

No live vault content lives here; real-world canary migration in productive
vaults is deferred until S03 (substrate extraction) ships and the new schema
has propagated via `wiki update`.
