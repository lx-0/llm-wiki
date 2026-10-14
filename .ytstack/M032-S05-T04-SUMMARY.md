---
milestone: M032
slice: S05
task: T04
project: llm-wiki
closed: 2026-10-14T16:38:00+02:00
verification: passed
---

# M032-S05-T04 -- Summary

## Commits

Committed together with this summary under the `M032-S05-T04:` ref — `git log --grep '^M032-S05-T04'`.

## Outcome

Cockpit and Atlas are gone whole: `cockpit.html`, `atlas.html`, `src/cockpit.ts`,
`src/atlas.ts`, the RGB type palette `src/lib/types.ts` only their canvases read, and
`src/index.css` (755 lines of HUD styling nothing else imported). Their IPC — three channels
and three `AppApi` methods — left `app/ipc.ts`, `preload.ts`, `main.ts` and the harness stub;
the renderer builds seven pages; the harness captures 58 states with every page strict. Every
window's first paint now follows the scheme (`windowBackground()` in `main.ts`: the surface
tokens' hex for light or dark) and the titles follow one pattern — "Inbox — llm-wiki" (was
"llm-wiki — Triage" on a hardcoded `#0b1220`), "Settings — llm-wiki", "Browse — llm-wiki",
"Overview — llm-wiki", "Welcome to llm-wiki". `marked` stays: the panel's answer rendering
uses it. With the legacy files gone, `biome check` reports zero findings for the first time
in the arc — the last three warnings (the reduced-motion `!important`s) carry a reason each.

## Deviations from plan

- No RED test preceded this task (pure removal); the gates were `tsc` + svelte-check for
  dangling imports, lint, the harness, and a Forge `package` of the slimmer bundle — all
  green on the first run.
- Window chrome went a step further than "Triage → Inbox": all five windows take the
  theme-aware background and the "X — llm-wiki" title, since the same `main.ts` blocks were
  open.
- The three remaining lint warnings were silenced with reasons rather than left standing;
  the rule is right in general and wrong for a reduced-motion override.

## Follow-ups

- T06 closeout: `desktop/README.md` still describes Cockpit/Atlas; the DECISIONS entry records
  the 2026-06-24 locks reopened (Svelte 5, Biome, Overview replaces the HUD windows).
- The `marked` dependency has one consumer left (`windows/panel/markdown.ts`); if the answer
  renderer ever moves to a hand-rolled subset, the dependency goes with it.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots … && npm run
package … && test ! -e <six files> && grep -rn -i "cockpit\|atlas" …` — passed (vitest 112
passed / 2 skipped; tsc + svelte-check 0 / 0; biome 0 errors, 0 warnings; harness 58
captures, 0 page errors, 0 layout / height failures; `package` exit 0 with seven renderer
pages; all six files absent; the grep prints nothing — "no references left"). The
theme-aware chrome is a main-process property the offscreen harness cannot show; the panel
captures are unchanged (index fresh 639 / 639).
