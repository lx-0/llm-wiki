---
milestone: M032
slice: S03
task: T01
project: llm-wiki
closed: 2026-10-14T20:40:00+02:00
verification: passed
---

# M032-S03-T01 -- Summary

## Commits

Committed together with this summary under the `M032-S03-T01:` ref — `git log --grep '^M032-S03-T01'`.

## Outcome

`src/styles/tokens.css` is the design system: cool-biased OKLCH neutrals (hue 250) for
surfaces/text/lines in light and dark (alpha borders in light, solid in dark; elevated stays
brightest in dark), the macOS system blue as the single accent, Apple's light/dark semantic
colours for ok / warn / danger, an eight-hue OKLCH wheel at one lightness/chroma per scheme for the
entity types (`--type-person` … `--type-note`), space 4–32, radius 6/10/14, type 11–28 with
weights 400/500/600, `tabular-nums`, 150 ms ease-out motion, a focus ring, reduced-motion
handling, and `.card` / `.row` / `.caps` layout classes; the panel scope keeps alpha card
surfaces for the native vibrancy material. First shared primitives: `ui/Button.svelte`
(primary / secondary / quiet, s / m, pressed + disabled states), `ui/Switch.svelte` (native
checkbox, label association), `ui/TypeBadge.svelte` (reads the type token, unknown kinds fall
back to note), `ui/icons.ts` (one 1.75-stroke inline set, 16 glyphs). The shared stylesheet
imports the tokens behind a legacy-alias block and lost its glow layers (`body.*::before/after`
radial gradients on panel / browse / settings / onboarding) and the `backdrop-filter` stack on
the panel header. The smoke page is now the primitives sheet (swatches, badges, buttons in every
state, switch rows, type scale, icons) that the harness captures at 600×1040 in light and dark.

## Deviations from plan

- Dark-mode semantic colours use Apple's dark-appearance values verbatim instead of a
  `color-mix` desaturation — the mixed green rendered olive in the first capture; Apple's dark
  set is already tuned for dark backgrounds.
- The primitives sheet survives until S05 closeout (useful for the remaining windows) instead of
  dying in T02; the S03 plan line was updated.

## Follow-ups

- `lib/types.ts` (RGB palette for the two canvases) now duplicates the type hues until S05
  deletes Cockpit + Atlas — tracked there.
- The three `!important` lines in the reduced-motion block are intentional (they must beat
  component transitions) and stay as Biome warnings.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots` + colour-literal audit —
passed (typecheck + svelte-check silent, vitest 63 passed / 1 skipped, biome 0 errors / 7
warnings, 30 captures with 0 page errors, 0 colour literals in `ui/*.svelte` + the sheet). Both
`smoke-{light,dark}-default.png` reviewed at full size: one primary button, badges read as one
family, no overlap/overflow.
