# Entity Pages — State + Timeline shape

Per-entity pages that accrete a "State" block (compiled truth) above the line and an "Append-only Timeline" below. Adopted from gbrain's two-layer page anatomy (`docs/GBRAIN_RECOMMENDED_SCHEMA.md`). See `gbrain-comparison.md` for the comparative rationale.

## The pattern

```markdown
---
title: "Jane Doe"
aliases: ["jane", "jane@acme.com"]
type: person
last_synthesized: 2026-05-13
sources: ["daily/2026-04-12.md", "raw/transcripts/jamie/2026-04-15--review--abc.md"]
---

# Jane Doe

> One-paragraph executive summary: who, role, why she matters to me.

## State
- **Role:** VP Eng, Acme
- **Relationship:** former colleague
- **Open threads:** waiting on her intro to Bob; promised to send Q3 deck

## What they're building
Prose, with `[[wikilinks]]` into concepts/projects.

## See also
- [[knowledge/projects/yesterday-platform]]
- [[knowledge/concepts/agent-config-staleness]]

---

## Timeline
- **2026-05-12** | `raw/transcripts/jamie/2026-04-15--review--abc.md` — Reviewed Q1 roadmap; she pushed back on the inference-cost framing.
- **2026-04-12** | `daily/2026-04-12.md` — Mentioned by user during agent-config debugging session.
```

## Why it matters now

- Jamie meetings (live since 2026-05-13) have `attendees`. They currently land in `raw/transcripts/jamie/<date>--<slug>.md` and nowhere aggregates "all meetings attended by Jane". The compile pass distills *content*, not *participation*.
- `daily/` mentions of people accumulate without ever rolling up.
- Atomic-article pattern works for `concepts/` and `qa/`. It under-aggregates for `people/` and `projects/`.

## Open design questions

- **Which folder is the anchor?** `knowledge/people/` is the strongest candidate (highest substrate volume from Jamie+daily+email); `knowledge/projects/` is plausible but lower-volume per entity. Decide in pitch phase, not here.
- **Coexistence with atomic articles.** Most likely answer: State+Timeline applies *only* to entity folders (`people/`, `projects/`, maybe later `companies/`); `concepts/`, `qa/`, `connections/` keep their current shape. Schema-split, not migration.
- **Timeline source granularity.** Per-substrate-file (one entry per source) or per-event (multiple entries for a single long meeting transcript)? Probably per-source for simplicity; revisit if entries become too dense.
- **Who writes the State block — LLM or operator?** Compile prompt rewrites State each pass from current substrate; operator edits get preserved only inside markers (analogous to dashboard agent-button markers). Or: State is fully LLM-owned, operator overrides go to `facts/` as today.
- **`compiled_from` provenance** stays in frontmatter; Timeline cites the same sources but with one-line context. Some duplication is OK.

## Touchpoints

- `prompts/compile_main.md` — type-conditional rule: for `type: person|project`, emit two-layer shape. For everything else, current atomic shape.
- `scripts/compile.py` — no engine change if prompt branches on type. Possible: pass an entity-folder hint into the prompt context.
- `scripts/lint.py` — new check `check_two_layer_pages`: for `type: person|project`, verify `## State` + `---` + `## Timeline` sections exist and Timeline entries are reverse-chronological.
- `scripts/pin.py` already exists for MOC-pinning — adjacent surface, could grow `wiki pin --append-timeline <entity> "<note>"` for operator-driven entries.
- `templates/AGENTS.example.md` — schema doc updated to describe the two shapes.

## Lift estimate

- Prompt branching + AGENTS.md doc: 0.5 day
- Lint check: 0.5 day
- Migration of 10-20 existing `people/` articles via re-compile: 1 day (mostly LLM time + spot-checks)
- Testing on Jamie meeting output (first 6 meetings → person-pages): 1 day

**~3 days end-to-end** for `people/` only. `projects/` extension adds ~1 day.

## Risks

1. **LLM struggles with the two-layer constraint.** Compile prompt rules accumulate; this adds one more conditional. Could fail silently (produces atomic-shape page anyway, lint catches it). Mitigation: structural lint flags non-conforming entity pages.
2. **Timeline grows unbounded.** A long-running collaborator-page could have 200+ Timeline entries over time. Mitigation: cap at last N (e.g. 50) with link to a `timeline-archive/<slug>.md` overflow file. Defer until any single page reaches the limit.
3. **State drift between facts/ and the State block.** A `facts/` entry says "Jane left Acme"; the State block still says "VP Eng, Acme". Mitigation: compile prompt reads facts FIRST and uses them to override State (already the existing facts mechanism).
4. **Conflict with current atomic `connections/`.** Some current `connections/` articles are de facto person-pages. Re-classification needed — handled by `wiki correct apply` per article.

## Ripens when

- First Jamie compile pass produces person-shaped output that wants aggregation (probably within 10-20 meetings).
- OR operator hits a "where is everything about Jane?" moment and has to grep `daily/` + `raw/transcripts/`.

## Status

Backlog. Sibling to `takes-substrate.md` and `dream-cycle.md` — the three form a coherent "entity-pages layer". One pitch should consider whether to bundle them as M005 or land independently.
