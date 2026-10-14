---
milestone: M032
slice: S03
project: llm-wiki
created: 2026-10-14T13:40:00+02:00
status: planned
task_count: 4
completed_tasks: 1
---

# M032-S03 -- Slice Plan

**Goal:** A token-based design system with one palette source replaces the pasted literals and the glow/HUD costume, and the four secondary windows (Settings, Onboarding, Browse, Triage) run as Svelte components on it — light and dark correct, copy on a diet, verified by the harness.

## Tasks

- [x] T01 -- Tokens + palette: `src/styles/tokens.css` (colour / space / radius / type scale, light + dark), `src/lib/palette.ts` as the single type-colour source applied as CSS custom properties at startup, shared `lib/` helpers (`time.ts`, `icons.ts`), the glow/blur/HUD/sparkle/emoji layers removed from the stylesheet.
- [ ] T02 -- Settings + Onboarding as Svelte windows (pilot): same behaviour, label + value instead of sub-sentences, one sentence per onboarding step; harness states light/dark. (The S01 smoke page lives on as the primitives sheet from T01 and is deleted at S05 closeout.)
- [ ] T03 -- Browse + Triage as Svelte windows: layouts kept, hardcoded dark hex gone (light-mode defect closed by construction), group hints and the triage sub-line cut to labels.
- [ ] T04 -- Old `settings.ts` / `onboarding.ts` / `browse.ts` / `triage.ts` + their CSS blocks deleted; screenshot gate (overlap, overflow, zoom-crop) over the four windows × light/dark; harness fixtures extended where a state was missing.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
