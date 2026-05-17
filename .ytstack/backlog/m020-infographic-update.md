# M020 infographic update — DONE 2026-05-17

**Status**: shipped in commit `afa7b51` via subagent dispatch; defensive re-render at `--scale 1` to match production PNG dimensions (3033×2976), no element moved or removed. See `.ytstack/DECISIONS.md` 2026-05-17 M020 entry for the broader arc.

**Edits landed**:

- `docs/architecture.excalidraw`: `compile_text` element (line ~3065) extended with a 7th line `· post-pass writes ## Backlinks footer per article`. Fits the existing 140 px `compile_rect` (7 lines × 14 px × 1.25 line-height = 122.5 px). No geometry change.
- `docs/overview.excalidraw`: `p2_resilience` (green caption under the compile.py pill) extended with `· articles carry ## Backlinks footer`. Free-floating, no container, no element moved.

**Verify steps run**: visual diff of before/after PNGs (no other elements changed); `--scale 1` re-render of both files after defensive scale=4 rendering hit the Chrome canvas-pixel ceiling.

---

# Original briefing (kept for posterity)

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
