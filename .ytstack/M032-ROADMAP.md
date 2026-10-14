---
milestone: M032
project: llm-wiki
size: L
created: 2026-10-14T13:10:00+02:00
status: planned
total_slices: 5
completed_slices: 0
---

# M032 Roadmap

**Goal:** The desktop app stops reading as vibe-coded — state as shapes, one action list,
costume off, renderer rebuilt on a component model with a modern toolchain and a committed
screenshot harness.

**Exit criteria:** see `M032-CONTEXT.md` (8 items: panel ≤ 640 px / zero paragraphs,
one action model fed by the engine JSON contract, three visual status tiles + persistent
result feedback, Overview replaces Cockpit + Atlas, tokens + light mode, TS 5 strict +
Biome + renderer tests, harness committed, blind learnability ≥ 8/10).

## Slices

Slice detail lives in per-slice `M032-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

Suggested framing (refine in slice-milestone; audit in `backlog/deslop-arc.md`):

- [ ] S01 -- **Harness + toolchain.** Port `/tmp/llmwiki-shots/render.py` into
      `desktop/scripts/` with checked-in fixtures (states: default / running / failed /
      no-access / empty, light + dark); TypeScript 4.5 → 5.x with `strict`, typecheck in
      `npm test`; ESLint → Biome; strip the Forge boilerplate (renderer comment,
      package.json name/description); dedupe `escapeHtml`/`fmtAgo`/icons/logo into `lib/`.
      Framework-independent. (~4 tasks)
- [ ] S02 -- **Engine contract + one action model.** `wiki menu --json` and
      `wiki doctor --json` gain `schema`, `title`, `verb`, `group`, `argv` (engine-side,
      consumer-grep: `menu_context`, `menu.py`, `health.py`, desktop, tests); the TUI reuses
      `title`; the app gets one `Action` type + merge/dedupe of doctor + menu + advanced;
      `friendly*`/`pendingVerb` deleted; unit tests for the merge. Closes the
      `home-screen-ux.md` lever-3 gap from the engine side if it falls out naturally.
      (~4 tasks)
- [ ] S03 -- **Design system + costume off.** Tokens (colour/space/radius/type, light +
      dark), single palette source generated into CSS, glow/blur/HUD/emoji/sparkle removal,
      light-mode defect on Triage/Settings fixed; if Svelte is chosen (open question 1)
      this slice starts with the scaffold and ports Settings + Onboarding as the pilot
      windows. Screenshot gate on every window. (~4 tasks)
- [ ] S04 -- **Panel rebuilt.** Labeled nav, status strip (Library sparkline · Health ring ·
      Capture meter), Next-up action list with row-level progress and persistent result
      pills, Recent, collapsed Add/Sources/Quit footer; copy diet (zero paragraphs,
      tooltips ≤ 6 words); old renderer removed in the swap commit; renderer tests for the
      status derivations. (~5 tasks)
- [ ] S05 -- **Overview window + closeout.** Four charts (adds per day, type distribution,
      health, capture timeline) + pending queue replace Cockpit + Atlas (deleted);
      Browse/Triage on tokens + copy diet; blind synthetic learnability run; DMG rebuild;
      `desktop/README.md` rewritten short; DECISIONS entry (2026-06-24 locks reopened),
      KNOWLEDGE (harness + Svelte/Biome gotchas), `docs/PROCESS.md` JSON-contract note.
      (~5 tasks)

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the
plan still fits reality. Open question 1 (framework) must be answered before S03 starts;
S01–S02 do not depend on it. Each slice ends with the harness screenshot gate and an
operator look at the rebuilt DMG.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
