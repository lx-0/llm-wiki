---
milestone: M028
slice: S04
project: llm-wiki
created: 2026-06-13T15:56:13+0200
status: done
task_count: 4
completed_tasks: 4
---

# M028-S04 -- Slice Plan

**Goal:** A first-class `supersession` status exists so `negation` stops
conflating *false* with *outdated*, and M028 is documented + issue #5 closed.

## Tasks

- [x] T01 -- Add `supersession` to `VALID_STATUS` in `scripts/facts/correct.py:54`
  + the `--status` `choices` (L228-232) + help text; semantics = "was true, now
  outdated → annotate, never delete." Wire it through `prompts/correct_apply.md`:
  `supersession` always annotates (never delete-eligible, even with
  `--allow-delete`); `negation` keeps the false-claim meaning and remains the only
  delete-eligible status (still opt-in per S01). Resolve the CONTEXT open-question
  (distinct status value, not a modifier).
- [x] T02 -- Extend lint in `scripts/facts/lint.py` (`check_facts_violations`) to
  handle `supersession`: surface articles that should carry the superseded
  banner/frontmatter but don't, as annotation gaps — not as deletion candidates.
  Keep `negation` lint behaviour intact.
- [x] T03 -- Docs + release: update `AGENTS.md` (fact schema + the supersede-default
  behaviour), `docs/PROCESS.md` (`correct apply` flow), the operator config
  reference for any new knob (S02 max-turns, S03 broad-term threshold), `CHANGELOG`
  + version bump; DECISIONS.md entry for the supersede-default decision; KNOWLEDGE.md
  for the no-Bash/engine-post-step pattern.
- [x] T04 -- Closeout: full suite green; the S01-T04 golden repro passes; comment on
  + close issue #5 with the shipped-fixes summary (operator-gated per REGEL); fold
  the new behaviour into the infographics only if portrait-worthy (likely a caption
  on the existing facts/correct box, not a new element — apply the steady-state +
  PNG-review gates from CLAUDE.md).

## Done when

All tasks marked `[x]` and verified. `supersession` is a real status with lint
support; the milestone is documented; issue #5 is closed.

## Notes

- T01 migration discipline: `VALID_STATUS` is a Python set, not a config knob — no
  `migrate_config_keys.py` entry needed for the enum itself. Only S02/S03 config
  knobs require migration entries (in their own slices).
- T04 issue-close is operator-gated (`gh issue close` only on explicit go); drafting
  the close comment is fine ahead of that.
