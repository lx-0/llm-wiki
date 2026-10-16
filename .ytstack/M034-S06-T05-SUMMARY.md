---
milestone: M034
slice: S06
task: T05
project: llm-wiki
closed: 2026-10-16T05:33:00+02:00
verification: passed
---

# M034-S06-T05 -- Summary

## Commits

- `c5f597c` -- M034-S06-T05 (fix): the home screen stops offering "Save today's AI chat" —
  its probe read the pre-rollup `daily/sessions/<date>.md` (the layout is
  `daily/<date>/sessions.md` since 2026-05-15), so it was 1 on every day in the TUI and the
  desktop, and the action ran a bare `wiki flush`, which prints its usage and exits 2 without
  a hook's context file; a guard refuses any action whose argv is a command that answers its
  bare form with help and a failing exit; the TUI header drops ✨ and the commit hash (one
  git child per redraw)
- `afe7124` -- M034-S06-T05: the surfaces carry what their readers use (exit criterion 7) —
  README 378 → 295 lines and AGENTS.md 326 → 248, each section named for its reader in the
  Contents, held by tests/test_doc_budget.py; AGENTS.md's six feature sections out
  (FEATURES / cli.md / config.md hold them; dream priority's resolution order moved to
  config.md), a feature-invariants list stays; README counts 14 collectors and 18 lint
  checks; the doc audit over the retired M034 names is clean; `dream sweep
  --selection-mode` help names the real default; 0.7.34

## Outcome

Exit criterion 7 is met. Criterion 5's TUI half is done too (the gate half was T02).

- **README.md** went from 378 to 295 lines, 32.1 to 26.3 KB. Its Contents group the sections
  by reader: deciding whether to use it, installing and running it, reading further or
  contributing.
  - **Gone:**
    - "Running scripts manually", which taught the bare `uv run` forms and said "Hooks always
      use Option B";
    - the commented-out star history;
    - the code-gates detail, which AGENTS.md "Style" holds;
    - "Foundations", which repeated the engine/vault and install sections for the same
      reader.
  - **Folded:** the maintenance-pass paragraphs became one list pointing at `docs/cli.md`.
  - **Rewritten:** the stale CLI paragraph ("bash stays the single source of truth",
    "49 commands") is now "Commands".
  - **Corrected:**
    - fourteen collectors, under today's names (the diagram groups them);
    - 18 lint checks;
    - eight instruments named (K6 and ASRS were missing);
    - `bash` with no "≥ 4": the bootstrap runs on macOS bash 3.2, and `wiki version` was
      checked under `/bin/bash` 3.2.57.
- **AGENTS.md** went from 326 to 248 lines, 48.8 to 29.7 KB. Its Contents group the sections
  by the change being made.
  - **Out:** the six feature sections (dream priority, reconcile, health-trends,
    web-research, dedup, usage). FEATURES.md rows 122–128, `docs/cli.md` and
    `docs/config.md` already held them.
  - **Kept:** what a change must keep, as a five-line "Feature invariants" list:
    - tokens, never dollars;
    - no Bash and a write scope for wiki-editing agents;
    - web research stays out of `raw/`;
    - link rewrites go through `core.links`;
    - double gates stay off.
  - **Shorter:**
    - the vault-layer lines (from 2–5 KB each);
    - the repo tree;
    - `compile_role`;
    - the intake-channel rule;
    - the gates paragraph.
  - **Fixed:** the two orphan bullets after the SDK rule are back under "Side effects".
- **`docs/config.md`** gained "Dream priority — how the weights combine", the only content
  that lived in AGENTS.md alone.
- **The TUI header** reads `wiki — <vault> vault`, and "Nothing pending" has no ✨.
  `_git_revision()` is gone, and with it a `git` child on every redraw.
- **`tests/test_doc_budget.py`** holds README ≤ 300 and AGENTS.md ≤ 250, as
  `test_bash_budget` holds the bootstrap.
- **The doc audit** (`/tmp/m034-doc-audit.sh`) covered 38 files: README, AGENTS.md,
  `docs/*.md`, skills and templates. It searched for the M034-retired names and their stale
  claims (the bash library, bash-owned commands and helpers, the by-path scripts, the old
  collector names, wrong counts, the pre-rollup session path, the TUI hash, ✨) and has
  0 hits.

## Deviations from plan

- **A defect fixed in passing, as its own commit (`c5f597c`).** The home screen's
  "Save today's AI chat" suggestion had two faults:
  - **Its probe always fired.** It read `daily/sessions/<today>.md`, a path unused since
    the 2026-05-15 rollup, so it reported 1 every day in the TUI and in the desktop's
    `menu --json`. The live lxw vault, read only, has 140 `daily/<date>/sessions.md` and no
    `daily/sessions/`.
  - **Its action failed.** It ran a bare `wiki flush`, which prints its usage and exits 2
    (checked on scratch). T01 had removed the menu entry for exactly that, but not this
    suggestion.
  - **The fix:** both are removed, and a guard in `test_actions.py` now refuses any action
    whose argv is a bare command that answers with help and a failing exit. It failed on
    `flush` before the removal.
  - **The tests that hid it:** the probe's unit tests and the oracle fixture had built
    `daily/sessions/` themselves. KNOWLEDGE.md and TECH-PATTERNS record the lesson.
  - **Goldens and docs:** `menu.json` and `menu-json` lost the entry (only that entry in
    the diff), and `cli.md`'s signal table was corrected against the code (seven rows, real
    argv).
- **The audit's hits outside README/AGENTS were fixed, not listed:**
  - `cli.md` still said "bash stays single source of truth";
  - PROCESS.md named `lib/seed.sh` as the wiring of the agent buttons;
  - PROCESS.md's lint-triage section had four queues including "missing backlinks" (three
    since 2026-07-22).
  - **The two exceptions:** FEATURES.md's ⚫ line for that check is a deliberate
    retired-feature record (the audit skips ⚫ lines), and "18 structural checks" was the
    audit's own substring match, fixed in its regex.
- **`dream sweep --selection-mode`:** its help said the default "reads from
  `piggybacks.dream_cycle.selection_mode`", a key nothing reads. AGENTS.md said "greedy". The
  code's default is `probabilistic`. The help, `config.md` and the CHANGELOG now say so.
- **"Named for its reader" is read as the Contents grouping each section by reader**, one
  place per file, rather than a label inside every section.
- **The doctor header keeps its revision.** `wiki doctor`'s "Vault health — … (commit …)" is
  a diagnostic report, where the engine revision helps; the criterion named the TUI.

## Follow-ups

- **T06 (release 0.8.0):**
  - the DECISIONS milestone entry cites criterion 7 with the numbers above (lines and bytes);
  - the infographics stay unless a box names a moved component. The audit found none in the
    reader docs; the `.excalidraw` files are T06's to check.
- **Backlog:** `bare-uv-run-forms-in-docs.md` now covers README fully (its section is gone)
  and AGENTS.md partly: the developer forms remain in "Python environment", qualified by its
  first paragraph. The rest is unchanged: `cli.md`'s one-shot scripts and the docstrings.
- **No context MCP in this session:** the generic lesson went into TECH-PATTERNS "Data
  Boundaries" as a second instance of the glob-that-matches-nothing entry.

## Verification

Commands:
- `uv run --frozen pytest tests/test_doc_budget.py tests/test_menu.py -q`. RED first: README
  378 and AGENTS.md 326 over budget, and the header test caught the render spawning
  `git rev-parse`. Then green. The action guard was RED on `['flush']` before the removal.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2679 passed, 1 skipped.
- `bash /tmp/ci-gates.sh`: clean.
- `bash /tmp/m034-doc-audit.sh`: 0 hits in 38 files. It started at 5, so the audit was seen
  to fire.
- Every in-page anchor in README, AGENTS.md, `config.md` and `cli.md` resolves to a heading
  (`/tmp/anchors.py`).
- CI on `afe7124` (with `c5f597c`): both runs green (`ci` 38845873750, `secrets-scan`
  38845873699).
