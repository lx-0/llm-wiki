# M019 diagrams update — add reports/ surface to architecture + overview

`docs/architecture.excalidraw` + `docs/overview.excalidraw` currently
have **zero references** to the M019 `reports/` surface (analyst /
study / operator-self-reports). This is a gap against the
`feedback_infographics_track_engine` memory rule: "reliability /
new-pillar features must hit both diagrams in the same arc as the
code". Updated rule from 2026-05-17 also says: **steady-state
portraits, not changelogs** — no SHIPPED-month bands, no milestone-id
badges, no date stamps.

## What's missing

M019 added a major new pillar: the `reports/` surface (vault root,
sibling of `knowledge/`), the inference contract (deterministic
per-instrument scoring), the deterministic meta-report
(`_summary.md` with radar/sparkline/timeline SVGs), and the two-pass
analyst layer (Pass-1 per-study + Pass-2 cross-study).

Both diagrams currently render the engine as compile-loop-centric.
Reports flows entirely orthogonal — air-gapped from compile, runs on
its own schedule, produces its own consumption surface. The diagrams
need to show this **separation** as well as the new shapes.

## Architectural elements to render

**On `docs/architecture.excalidraw` (deep-dive technical):**

- A new pillar/cluster labeled `reports/` (vault root sibling of
  `knowledge/`) with three sub-boxes:
  - `studies/<id>/` (manifest + runs + state)
  - `runs/<ts>/instruments/<slug>.md` (per-instrument det. reports)
  - `runs/<ts>/_summary.md` + `_analysis.md` + `charts/*.svg`
  - `analyses/<ts>.md` (cross-study Pass-2 outputs)
- The Studies-CLI entry-point (`wiki study run / list / new`).
- The Analyst-CLI entry-point (`wiki analyze`).
- A pipeline arrow showing `study run` → inference (Claude SDK) →
  scoring (deterministic) → atomic persist → Pass-1 analyst → output.
- A pipeline arrow showing `analyze --cross-study-only` → reads
  Pass-1 outputs → Pass-2 analyst → output.
- The **air-gap** rendered as a hard separator: reports/ is NOT a
  substrate source for compile.py. Should be visually distinct from
  `daily/`, `raw/`, `knowledge/` which DO feed compile.

**On `docs/overview.excalidraw` (Grafana-style README hero):**

- A new top-level capability card/pill: "operator-self-reports"
  with a one-line subtitle ("5 clinical screens × weekly × analyst
  layer"). Stat-card style.
- Updated substrate-input counts if appropriate.
- The reports/ surface as one of the operator-facing outputs
  alongside `knowledge/`, dashboard, etc.

## Constraints (per `feedback_infographics_track_engine` 2026-05-17 update)

- **NO** "SHIPPED MAY 2026" / "M019" / date stamps anywhere in the
  canvas. Steady-state portraits only.
- New capability folded into existing structure — bump a stat-card
  if a count moved, add a chip to a substrate list, extend a
  pillar's description in present tense.
- If a feature has no steady-state slot, document in
  `docs/PROCESS.md` instead.

## Engineering plan (per `excalidraw-diagram` skill)

1. **Read both files**, sketch in prose what the new layout will be
   (boxes, arrows, palette, positioning).
2. **First pass:** add the new pillar / cards. Render the PNG.
3. **Second pass:** verify positioning (no overlaps, no overflow),
   readable text sizes, arrow source/target accuracy. Re-render.
4. **Third pass:** cleanup details — font sizes, color consistency,
   group bindings, containerId / boundElements on bound text.
5. Commit both `.excalidraw` files + their rendered `.png` siblings.

Rough size: S-M (~half-day to one day). Render-validate loop
typically dominates the time, not the JSON-editing itself.

## Ripens when

- M019 dogfooding produces enough operator-side signal that the
  diagrams genuinely need to match the reality. Today is fine to
  start — the architecture is locked in DECISIONS.md and won't
  change shape with operator feedback.
- OR before any public sharing of the engine (README, blog, demo).
  Diagrams are a public-facing artifact; "engine has reports surface
  but diagrams don't show it" reads as confusion.

## Status

**BACKLOGGED** — 2026-05-17 by M019 closeout. Engineering deliverable
in M019 is done; this is the diagram-update arc that completes the
"same arc as code" rule. Honest-but-deferred per session-tail
context discipline.
