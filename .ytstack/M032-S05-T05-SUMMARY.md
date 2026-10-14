---
milestone: M032
slice: S05
task: T05
project: llm-wiki
closed: 2026-10-14T17:40:00+02:00
verification: passed_with_caveats
---

# M032-S05-T05 -- Summary

## Commits

Committed together with this summary under the `M032-S05-T05:` ref — `git log --grep '^M032-S05-T05'`.

## Outcome

The blind panel ran as planned (`.ytstack/reviews/2026-10-14-desktop-learnability-panel.md`):
seven personas, six light captures in first-run order, a situational frame that never names a
screen, an eight-question task quiz whose key only the distiller saw, a 1–10 day-one
confidence rating. Phase 1 scores before any fix: Sam 6, Nova 6, Mateo 5 (novice mean 5.7),
Priya 6, Riley 4, Devin 6, Jess 5. Phase 2 located one defect every persona shared: nobody
could find how to stop the recording (Q4 wrong or "can't tell" seven times) — the green
capture tile hid Start / Stop behind an unlabeled expand and Settings showed the word
"Recording" where the welcome's switch had been. Consensus list after that: "Session capture
isn't installed" read as the recording being broken; 42 notes vs 2,024 in the same build; an
Ollama line in Health with a terminal-looking command and no button; "note index … Rebuild";
"lxw" unexplained; "+ Add link" invisible; Inbox 5 vs 9; blue dots nobody could name; Ask vs
Search.

What the app does now, after two fix rounds: the panel's capture tile is the control — a red
dot while recording, "Recording" / "Paused", an always-visible Pause / Resume button, no
expansion; Settings' capture row is a switch; the welcome's consent text says what is recorded
and where to pause it, and names the Obsidian vault path. Engine titles carry the verb the
desktop shows (`scripts/core/health.py`, `scripts/core/actions.py`): "AI chats aren't being
saved · Set up", "Saving your AI chats has stalled", "{n} AI chat(s) waiting to be saved", the
Ollama fix is "start Ollama on {host}" with the config alternative in the message, index drift
is "Fix", "{n} new files to sort into your library", "{n} new items to add to your library",
"{n} folder-scan requests to review", "Save today's AI chat to your library". The Ask field
reads "Ask your library anything…"; the footer's "+ Save a web page" is a button; the header
says "Library · lxw"; Recent's new-dot has a tooltip; Browse filters "notes by title" and
counts "42 notes" without the rail; Inbox rows say "from an AI chat" / "a voice memo", Keep /
Dismiss carry tooltips, the "unsure" pill is ink on tint; Overview's Next up lists the menu's
rows with fix hints as sub-lines, Health rows sort by severity, Update app is secondary.
Fixtures: `articleCount` derives from the list (42 everywhere), the `capture-open` harness
state became `paused`, and the harness measures content heights so the welcome (460 × 480) and
Settings (400 × 320) windows fit their copy.

Re-test (same blind prompt, three novice lenses, fresh captures): round 1 Sam 6 / Nova 7 /
Mateo 6, round 2 identical — **novice mean 6.3; exit criterion 8 (≥ 8/10) is not met**. What
the rounds did buy: every persona now answers "how do I stop the recording"; the "switch
disappeared after Get started" trust failure, the 42 / 2,024 contradiction and the two-kinds-
of-capture collision are gone. What keeps the score at 6, in order of weight (the review file
has the full gap analysis): a Health row the GUI cannot act on (Ollama — all three give-up
points in round 2), the pre-ticked capture switch on the welcome (M029's consented-capture
decision, reported not overturned), engine vocabulary one layer too deep for a novice
("folder-scan requests", "Fix" on a note list, type NOTE among notes, "vault" leaking from the
path line and fixture content), and the static-screenshot ceiling — no persona could see what
Fix, Ask or Save a web page do next.

DMG rebuilt on the final state: `desktop/out/make/dmg/arm64/llm-wiki-1.0.0-arm64.dmg`
(117 MB, 2026-10-14 17:33). **The operator's look at the installed app is pending** — open the
DMG, install over the running copy, check: menu-bar panel opens at rest height without a
scrollbar; the capture tile shows the red dot and the Pause button; Settings' switch flips the
listener; Welcome fits its text; Overview opens from the panel nav; Inbox title reads "Inbox —
llm-wiki"; light and dark both.

## Deviations from plan

- Two fix rounds instead of one. Round 1 (controls + copy + fixtures) moved the novice mean
  5.7 → 6.3; round 2 was a copy-only pass on the engine titles plus a corrected frame ("your
  friend installed it last week") to remove the "it recorded me before it said hello" confound
  — same 6.3. The gate stays unmet; T06 decides what the milestone records.
- The fix scope crossed into the engine. The titles the panel tripped over are produced by
  `scripts/core/health.py` / `scripts/core/actions.py` (`VERB_BY_COMMAND`), so those, their
  tests, `scripts/menu_context.py` and `docs/cli.md` changed alongside `desktop/src/**`; the
  plan had named desktop files only.
- Harness changes: a `contentHeights` measure in `capture.cjs` (max bottom edge of text /
  control elements per window) so window sizes are checked against copy, and the fixture's
  article count derived rather than typed.
- `desktop/src/ui/Meter.svelte` deleted: the capture meters it drew (S04-T02) were replaced by
  the control tile in round 1, and a repo-wide grep found no consumer left — a dead primitive
  in a de-slop arc is slop.
- One token moved: `--text-faint` 64% → 56% lightness (≈ 4.5:1 on `--bg`) — the panel's
  "quietest text" complaint from three personas.
- The review file was stamped with the wrong day by the planning session (2026-10-15 while
  the clock, the commits and the build all say 2026-10-14); renamed before commit, references
  updated. The committed T04 summary and S05 plan notes carried the same slip; the plan notes
  are corrected in this commit, the T04 summary is left as committed.

## Follow-ups

- T06 closeout carries the panel's outcome into `DECISIONS.md`: criterion 8 closed unmet at
  6.3 / 10 after two rounds, with the four blockers and Jess's premise challenge (the
  "mass-pattern" verdict and "should a note app record the mic at all") recorded for the
  operator, not acted on.
- `.ytstack/backlog/desktop-learnability-residue.md`: (1) non-dispatchable Health checks out
  of the issue count — the top lever, an operator decision because it changes what `wiki
  doctor`'s count means; (2) a vocabulary pass over the engine titles with the panel's word
  list; (3) a click-through learnability method (dev build, scripted first run) because the
  static-screenshot method has hit its ceiling.
- The DMG look (above) is the operator's; the summary records it as pending.

## Verification

Command: `cd desktop && npm test && rtk proxy npm run lint && npm run shots … && npm run dmg
… && ls -la out/make/dmg/*/ && grep -n "re-test\|Re-test" …` — passed with caveats. vitest
112 passed / 2 skipped; tsc + svelte-check 472 files, 0 errors, 0 warnings; biome 78 files,
no findings; harness 58 captures, 0 page errors, 0 layout / height failures, panel fresh
639 / 639; engine `uv run pytest` 2025 passed / 1 skipped; `npm run dmg` exit 0,
`llm-wiki-1.0.0-arm64.dmg` 117 MB; the review file has Phase 1 + Phase 2 for seven personas,
the fix list, and two re-test sections. Caveat: the re-test's novice mean is 6.3, below the
plan's ≥ 8; the operator look at the installed app is pending.
