# M020 infographic update (deferred)

**Owed**: per memory `feedback_infographics_track_engine` ("reliability/fallback features must hit both `docs/architecture.excalidraw` + `docs/overview.excalidraw` in the same arc as code; 'wrong abstraction level' is rationalization, render it first").

**Reason for defer**: the M020 ship arc ran without the shared `excalidraw-diagram` skill loaded. Render-script lives in that skill bundle (per memory `project_skills_consolidation_local_to_shared` — consolidated 2026-05-15, repo-local copy at `skills/excalidraw-diagram/references/render_excalidraw.py` no longer present). Mutating a 10K+ line Excalidraw JSON without the render-verify loop is high-risk per memory `feedback_excalidraw_full_diagram_pitfalls` (this file specifically: `boundElements: []` not null, `index: b8X` form, sort by index, theme matters).

## What to update (steady-state, not changelog)

Per CLAUDE.md hard rule: no "SHIPPED M020" labels, no date stamps, no milestone-id badges. Fold into existing structure.

**architecture.excalidraw**:

1. Extend the `compile_text` element (line 3065+) description to mention the post-pass: append something like `· post-pass writes ## Backlinks footer per article (sentinel-managed)` to the existing label.
2. Optional — add a small chip near the knowledge/ band footer noting that articles carry their own `## Backlinks` block (steady-state property of the compiled artifact).

**overview.excalidraw**:

1. The substrate-footer / output-band area is the right spot. A 1-line addition like "· articles carry incoming-link footer" on whichever pill describes knowledge/ output.

## Verify before claiming done

1. Light + dark theme render against the committed PNG (matched theme).
2. No element moved or removed (operator's spatial map must not shift).
3. PNG re-rendered via shared `excalidraw-diagram` skill's `render_excalidraw.py`, output committed alongside the JSON.

## Trigger to pick this up

Next session that already has the `excalidraw-diagram` skill loaded for an unrelated reason — fold in. Or when the operator flags the diagrams as drift-out-of-date during a doc review.
