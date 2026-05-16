---
milestone: M007
project: llm-wiki
created: 2026-05-16T15:01:00Z
size: M
---

# M007 -- Context

## Goal

Ship a `compile_role` frontmatter axis with 3 values that lets compile.py treat any vault page as substrate (distill into knowledge/), source-and-final (index without distilling), or final-only (engine-skip).

## Exit criteria

1. `compile_role` enum (`source-only | source-and-final | final-only`) recognized in frontmatter + lint-validated.
2. compile.py branches 3-way: `source-only` behaves as today (distill into knowledge/); `source-and-final` indexed-only (mentions + backlinks, no separate distilled article); `final-only` skipped entirely.
3. Dashboard + MOC auto-includes + `wiki query` filter `final-only` out of active surfaces by default; opt-in via `--include-final-only` flag.
4. ≥1 longform import from `imported/lx/` tagged `compile_role: source-and-final` and surfacing correctly via Obsidian search + `knowledge/index.md`.
5. `archives-flag.md` backlog retired (subsumed) — no parallel `archived: true` mechanism shipped.

## Size

M — see `M007-ROADMAP.md` for slice breakdown. Lift estimate from backlog: ~3.5 days.

## Decisions locked in discuss phase

- 2026-05-16: chose generic `compile_role` axis over binary `archived: true` (`archives-flag.md`). Reason: absorbs both the cold-state need AND the long-form-deliberate-writing gap surfaced by operator's own 2026-05-02 vault-architecture plan. Schema migrations are easier with one mental model than two.
- 2026-05-16: default-by-location inference (raw/ → source-only, knowledge/ → final-only-or-default-distilled). Explicit `compile_role` in frontmatter overrides. Lint warns on cross-location moves without explicit override.
- 2026-05-16: `source-and-final` semantics = compile extracts wikilinks + builds backlinks + surfaces in `knowledge/index.md` with its own pathname, but does NOT produce a separate `knowledge/concepts/<title>.md`. Indexed, not distilled.

## Open questions

- **MOC behavior for `source-and-final`** — should longform essays appear in MOC auto-includes? Probably yes (deliberate writing should be discoverable). Distinct from `final-only` which hides.
- **`final-only` in raw/?** — could an operator pin a raw/ file as "don't recompile, leave alone"? Edge case; decide during slicing if any concrete demand surfaces.
- **Lint cross-location-move warning** — exact mechanism (git history vs frontmatter `previous_location`) deferred to plan-task phase.
- **Migration tooling** — if anyone manually flagged `archived: true` between now and M007 ship, a one-time `archived: true` → `compile_role: final-only` sed-pass needed. Check before ship.
