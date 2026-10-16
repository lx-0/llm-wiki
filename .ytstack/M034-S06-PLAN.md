---
milestone: M034
slice: S06
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 6
completed_tasks: 0
---

# M034-S06 -- Slice Plan

**Goal:** The surfaces are cut and the milestone closes:
- one command table behind help and the home menu;
- command output through `core/console`, with a gate;
- collectors registered lazily behind one collect verb;
- README ≤ 300 and AGENTS.md ≤ 250;
- release 0.8.0 and the backlog reconciled.

## Tasks

- [ ] T01 -- One table. The home menu's quick actions, categories and fuzzy catalogue derive
  from `cli_catalog`, with `core/actions` for the pending-work rows. A test refuses a menu
  entry whose argv names no catalogue command. The hand-curated lists are deleted; the
  menu's golden is unchanged, apart from differences decided in the commit. Also: `menu.py`'s
  non-TTY fallback still spawns `wiki help` (bash → python → python) and can print
  `cli.render_help()` in-process. The output is the same (`menu-no-tty` golden); noted in
  S01-T05.
- [ ] T02 -- `print` → `core/console` across the command modules. A gate refuses `print(` in
  command modules outside an allowlist with reasons (JSON payload writers and the TUI frame
  writer among them). The count goes before → after; `--json` stays payload-only.
- [ ] T03 -- Collectors: a name → module table with lazy registration (`wiki collect --list`
  imports no collector module, guarded by a test), and `wiki collect <name> -- <flags>` passed
  through to the collectors' `main(argv)`. The three by-path entry scripts and PROCESS.md's
  second invocation form are deleted.

  This includes every bare `uv run --project .wiki …` line PROCESS.md still teaches; there
  were 12 at S01-T07: the `scan_*` flags, `collectors.cli`, and `dashboard.dashboard_stats`
  / `dashboard_lint`. Each becomes a `wiki` command. On an iCloud vault the bare form
  ignores the engine's environment location and recreates the in-vault venv. S01-T07 fixed
  the same defect in the use-llm-wiki skill (`wiki stats`).
- [ ] T04 -- Surfaces: `README.md` ≤ 300 lines and `AGENTS.md` ≤ 250, each section naming its
  reader; the TUI's ✨ glyph and the commit hash in its header are removed. The doc audit
  finds no stale names.
- [ ] T05 -- Release 0.8.0:
  - CHANGELOG with the "For your vault" section, version and lock;
  - engine-layout, FEATURES and cli.md current;
  - the DECISIONS milestone entry against the nine exit criteria;
  - the infographics by rule: change only if a box names a moved component.
- [ ] T06 -- Milestone close: the full backlog fan-out against the code (DECISIONS 2026-08-27
  method), PRIORITY.md re-cut, then `ytstack:reassess-roadmap` for the last slice.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; all nine exit criteria met.

## Notes

The arc ends here. What the arc table left out (§8: the excalidraw diagrams, signing and
auto-update, the ytstack process files) stays out.

**What S05 taught for this slice** (reassessment after S05, outcome A: the slice order
holds):
- **Exit criteria 1 and 8 are met.** `wiki` is a 129-line bootstrap with no library
  (`test_bash_budget.py`), and the operator path ran on scratch (`M034-S05-T06-SUMMARY.md`).
  T05's DECISIONS entry cites them, with T06's open caveat: the LLM round trip could not run
  under a sandboxed HOME.
- **T02's print gate has a seam already.** Every help text goes through
  `cli_help.print_help`, a print site the gate allowlists with its reason (T04 refuses any
  other `print(H_…)`).
- **A seam guard scans every engine file, not only `*.py`.** S05-T02's grammar guard missed
  a copy in `wiki` until it looked at the bash too. T01's "no menu entry without a
  catalogue command" and T02's gate should not leave the TUI or the desktop's spawn args out
  by file type.
- **A port that touches about ten files splits at its natural seam.** Update split by phase,
  and the intermediate state was the cross-version path itself. T03's collector registry
  can split the same way: the table and lazy listing first, then the verb's pass-through.
- **Goldens hold the steady state; transitions are asserted.** Where a record would move
  with unrelated config (the migration's 120 keys), prepare the steady state and assert the
  change separately.
- **New backlog for T06's fan-out:** `update-hooks-hint-only-when-stale.md`,
  `compile-exit-code-on-failure.md`.
