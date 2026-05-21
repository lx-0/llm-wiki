# Infographic touch for gmeet email-discovery (M024)

**Status:** deferred from M024-S03 (2026-05-21).

## What

M024 gave the gmeet collector a second discovery source (email-link scan of
`gemini-notes@google.com` mails → colleague-shared meetings). Per
`feedback_infographics_track_engine`, a behaviour change should be reflected in
`docs/architecture.excalidraw` + `docs/overview.excalidraw`.

## Why deferred (not skipped)

The change is a *discovery-source refinement* on an existing box, not a new
pillar — so per the steady-state-portrait rule it folds into the gmeet box's
description text rather than adding elements. But any `.excalidraw` edit must
pass the three render-review gates (bbox-overlap scan, glyph-width scan, visual
zoom-crop review) before it can be claimed done, plus the scale-fallback
renderer caveat. Doing that half-way under a "go straight to push" mandate would
violate the review-before-done hard rule. Cleaner to do it as its own focused
pass.

## How (when picked up)

- gmeet box description in BOTH excalidraw files: extend to note "two discovery
  sources: own-Drive folder scan + email-announced colleague meetings" (text
  only, no new elements).
- Re-render via repo-local `skills/excalidraw-diagram/references/render_excalidraw.py`.
- Run all three gates; zoom-crop the gmeet box region at ≥1600px.
- If the box can't hold the extra line legibly, tighten font or wrap — don't
  overflow.

## Pointers

- Steady-state rule + render-review gates: project `CLAUDE.md` hard rules.
- Memory: `feedback_infographics_track_engine`, `project_overview_diagram`.
