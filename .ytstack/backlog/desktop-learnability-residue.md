---
name: Desktop learnability residue — what the blind panel left at 6.3 / 10
description: Three follow-ups from the M032-S05-T05 blind first-run panel (novice mean 6.3 after two fix rounds, gate was 8). Non-dispatchable Health checks out of the issue count (operator decision), an engine-title vocabulary pass, and a click-through test method to replace static screenshots.
type: project
---

# Desktop learnability residue

Source: `.ytstack/reviews/2026-10-14-desktop-learnability-panel.md` (frame, quiz, per-persona
distillation, both fix rounds, gap analysis). Scores on the same blind method: M029 closed at
6 / 10; M032-S05-T05 measured 5.7 before fixes and 6.3 after two rounds (Sam 6 / Nova 7 /
Mateo 6). Exit criterion 8 of M032 (≥ 8 / 10) stays unmet; the milestone records that honestly
rather than running a third copy round for the same number.

## 1. Non-dispatchable Health checks out of the issue count (operator decision)

**Finding.** The Ollama "unreachable" row was the give-up point for all three novice lenses in
round 2: the desktop counts it among "3 issues", renders the fix hint ("start Ollama on
kcma-d8") and offers no button, because the engine has nothing it can run. A first-run reader
meets a problem with no action and stops there.

**Options.** (a) Render checks whose `fix` is not dispatchable (no `command` in the schema-2
contract) in a quiet "for whoever set this up" block under the actionable rows and exclude them
from the ring's red count; (b) make the local-AI reachability check info-level on the desktop
while `wiki doctor` keeps it as a warning; (c) leave it — a down LLM host is an issue, and the
count should say so.

**Why it is an operator decision.** (a) and (b) change what the doctor's number means on one
surface; the engine's count and the desktop's would differ. Recommendation: (a) — the count
stays truthful in the CLI, the desktop separates "you can fix this here" from "someone with a
terminal can", and the panel's top blocker goes away without touching `health.py`.

## 2. Engine-title vocabulary pass

Words the novice lenses still stumble on after round 2, with the source each comes from:

| Word on screen | Source | What the persona asked |
| --- | --- | --- |
| "folder-scan requests to review" | `actions.py` curiosity-folder | "who is requesting?" |
| "files to sort" vs "items to add" | process-inbox vs compile titles | "are files and items the same thing?" |
| "Fix" on "note list is out of date" | `VERB_BY_COMMAND[reindex]` | "what will it do to my notes?" |
| "Set up" for AI chats | `VERB_BY_COMMAND[hooks]` | "what will it ask of me?" |
| type `NOTE` among notes | `TypeBadge` label for `note` | "aren't they all notes?" |
| "vault" | welcome path line, Inbox fixture content | "is a vault the library?" |
| "dream cycle" | fixture content only | — (fixture, not UI copy) |

Each is a copy change in `scripts/core/actions.py` / `health.py` + tests + `docs/cli.md`
(the engine owns the titles since round 1). Diminishing returns per round on the static
method; do this together with item 3, not before it.

## 3. Click-through learnability method

Every persona named a hypothetical give-up the screenshots cannot answer: what an answer looks
like, what Fix does, what Save a web page asks next, whether Pause actually pauses. The
static-screenshot method has hit its ceiling at ~6; the next measurable gain needs a scripted
first run — dev build, the harness driving the real windows through the quiz tasks (open
panel → ask → read answer; click Pause → read the tile; click Save a web page → read what
appears) and handing the personas the resulting sequence (or a short screen recording per
task). The harness already renders every window headless and knows the fixture states; the
missing piece is a task script that captures *after* each interaction.
