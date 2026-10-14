---
milestone: M032
slice: S05
task: T06
project: llm-wiki
closed: 2026-10-14T18:15:00+02:00
verification: passed
---

# M032-S05-T06 -- Summary

## Commits

Two commits under the `M032-S05-T06:` ref — `git log --grep '^M032-S05-T06'`: `6b917da`
holds only the smoke-page deletions (the staging command listed the already-`git rm`-ed
paths, `git add` rejected the pathspec and the commit went out with what was staged; it was
pushed before the gap was seen, so it stays), and the follow-up commit holds everything else
together with this summary.

## Outcome

The documentation and release state describe the shipped app. `desktop/README.md` (126
lines) names what a reader sees — the panel's Ask, Library / Health / Capture tiles with the
Pause / Resume control, Next up, Recent, the footer and header — and the five windows,
install, file access, start at login, the dev loop with `npm run shots` as the gate, the
source layout, build and the signed-build runbook; no Cockpit, Atlas, collapsible Settings or
`●◍` glyph residue. `DECISIONS.md` carries one dated entry: the 2026-06-22 design locks
superseded (glow, HUD-only labels, "dense panel not gutted"), "plain English" kept with its
mechanism moved into the engine contract, the capture tile as control over the planned level
meter, criterion 6 measured (largest renderer component 284 lines of code + 216 of style),
criterion 8 closed unmet at 6.3 / 10 with the operator's levers and Jess's verdicts recorded.
`KNOWLEDGE.md` gains the `contentHeights` rule (window sizes from a measurement; the M029
clipped-window class recurred once copy grew). `docs/PROCESS.md` has a §19 "Operator
surfaces" — one action catalogue, schema 2 fields, the desktop renders words verbatim, three
title rules from the panel — and the overview table lists nineteen processes. `CHANGELOG.md`
opens with `[0.6.0] — 2026-10-14` (Added: schema-2 contract + rebuilt desktop app; Changed:
operator-facing titles; Removed: Cockpit + Atlas + the regex vocabulary layers);
`pyproject.toml` and `uv.lock` say 0.6.0. The smoke page is gone — `smoke.html`,
`src/windows/smoke/{main.ts,Smoke.svelte}` deleted, its entries removed from the Vite page
list and the harness surfaces — so the renderer builds six pages and the harness captures
56 states.

## Deviations from plan

- README is 126 lines against the plan's "≤ ~110": the signed + notarized runbook was kept
  whole rather than trimmed into prose, since it is the one part a non-engineer follows
  step by step.
- KNOWLEDGE received one new bullet, not four: the Svelte 5 + Forge 8 / Vite 8, Biome
  partial-`.svelte` and TypeScript 5 strict entries had already landed with S01–S04; only
  the window-size measurement was missing.
- The design-lock entry M032-CONTEXT calls "2026-06-24" is dated 2026-06-22 in DECISIONS;
  the new entry references the real heading.
- There is no global `.ytstack/ROADMAP.md` in this repo (the ytstack template's "flip the
  milestone in the global roadmap" step has nothing to act on); the milestone roadmap's
  `status` flips at reassess.

## Follow-ups

- `ytstack:reassess-roadmap` closes S05 and, with it, M032 (last slice); then the
  milestone-close backlog reconcile (DECISIONS 2026-08-27) before `plan-milestone` M033.
- `desktop/src/main.ts` at 509 lines is the next split candidate (main process; not a
  renderer module) — M034's surface diet.
- The DMG is rebuilt after this closeout (`desktop/out/make/dmg/arm64/llm-wiki-1.0.0-arm64.dmg`);
  the operator's look at the installed app stays pending, checklist in the T05 summary.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots … && test ! -e
smoke.html && test ! -e src/windows/smoke && grep … | wc -l; cd .. && uv run pytest -q && grep
0.6.0 CHANGELOG.md / pyproject.toml / uv.lock` — passed. tsc + svelte-check 469 files, 0 errors,
0 warnings; vitest 112 passed / 2 skipped; biome 77 files, no findings; harness 56 captures,
six pages built, 0 page errors, 0 layout / height failures, panel fresh 639 / 639; both smoke
paths absent; the residue grep (smoke page, cockpit, atlas over README, src, Vite config,
harness, Forge config, package.json) prints nothing; `uv run pytest` 2025 passed / 1 skipped;
`uv lock` reported `llm-wiki v0.5.4 -> v0.6.0`, and CHANGELOG line 21, pyproject line 3 and
uv.lock line 461 agree on 0.6.0.
