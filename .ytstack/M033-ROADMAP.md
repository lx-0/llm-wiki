---
milestone: M033
project: llm-wiki
size: L
created: 2026-10-14T18:40:00+02:00
status: planned
total_slices: 5
completed_slices: 4
---

# M033 Roadmap

**Goal:** The engine's Python is formatted, linted and type-checked by gates that run before
every commit and in CI; `scripts/` is an importable package; duplicate parsers and helpers
fold back onto the 0.3.0 seams; the unreadable functions are split — with the suite proving
at every step that nothing changed.

**Exit criteria:** see `M033-CONTEXT.md` (9 items: format + lint gates with reasons for every
ignore, 0 unused `noqa`, CI runs both suites, `scripts/` a package with `-m` dispatch and one
module identity, seams not copies, no function ≥ 150 lines, type checker green on `core/`,
schema-2 contracts typed once, behaviour byte-identical on a fixture vault).

## Slices

Slice detail lives in per-slice `M033-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

Suggested framing (refine in slice-milestone; audit in `backlog/deslop-arc.md` §3):

- [x] S01 -- **Gates first.** Fixture-vault snapshot test for the `--json`
      payloads and `wiki status` (the behaviour oracle for every later slice); the mechanical
      `ruff format` commit + `.git-blame-ignore-revs`; `[tool.ruff.lint]` policy with the
      finding buckets fixed or ignored-with-reason; `RUF100` → 0; ruff in pre-commit;
      `ci.yml` running pytest + ruff + the desktop suite.
- [x] S02 -- **`scripts/` as the one source root** (shipped as layout A, not a package —
      DECISIONS 2026-10-14): the five hyphenated scripts renamed with every call site, the 83
      `sys.path.insert` lines removed in favour of `hooks/_bootstrap.py`, `core/entry.py` as
      the one spawn seam (`python -m <module>` with `scripts/` on PYTHONPATH), the layout
      guard (KNOWLEDGE C01 closed), the operator path proven on scratch copies (`wiki update`
      re-executes the pulled engine), the 72 documented invocations rewritten (six tasks).
- [x] S03 -- **Seams, not copies** (shipped 2026-10-14/15, seven tasks): frontmatter
      17 + 8 unnamed grammars → one (`core/frontmatter`, a line-level guard measures exit
      criterion 5), slugify 7 → 1 (`core/utils.slugify`, two grammars as a keyword), logging
      33 `basicConfig` + 4 `_setup_logging` + 8 import-time calls → one entry-point setup
      (`core/console`), state 7 hand-rolled JSON writers → `core/state_store.store_for`,
      daily-rollup skeleton + 6 hand-typed appends → `daily_capture.rollup_line` +
      `base.append_rollup`, the `_scan_inbox` bindings inlined onto `base.scan_inbox`; every
      fold by mechanism-smell grep, parity on the operator vault, a guard per seam. `print`
      → `core/console` is NOT in this slice (too broad; M034 with the Python dispatcher).
- [x] S04 -- **Readable functions** (shipped 2026-10-15, seven tasks): the AST length gate
      (`tests/test_function_length.py`) measured 20 functions ≥ 150 lines, not 15, and all
      20 were split along their phases with characterisation tests first where a body had
      none; the ALLOWLIST is empty (0 of 1,503). The god modules split where it pays —
      `core/health/` package, `lint` model / checks / schema, `cli` help / catalogue /
      dispatch, `core/sdk_scope.py`, `adapters/drive/google.py`, `dream_model` /
      `dream_corpus` / `dream_priority`. A module-size gate (`tests/test_module_size.py`)
      holds every module ≤ 1,000 lines unless `docs/engine-layout.md` § "Large modules" gives
      the reason (four do). Every move was AST- or parity-proven, and stale test patches
      raise instead of silently isolating nothing.
- [ ] S05 -- **Types + closeout.** Type-checker probe and gate on `core/`;
      schema-2 contracts as one JSON Schema validated by both suites; `docs/engine-layout.md`
      + CHANGELOG 0.7.0 + DECISIONS + KNOWLEDGE; full backlog fan-out at close;
      `ytstack:reassess-roadmap`.

**Reassess after S01 (2026-10-14): A — proceed as planned.** S01 shipped the oracle, the
format commit, the lint policy, a clean `ruff check` and the gates (CI green on
`985a620`). What S01 learned that S02 inherits: there are *two* import identities in the
tree today — most modules import `core.*` with `scripts/` on `sys.path`, while `study.py`,
`analyze.py` and `reports/_engine/**` import `scripts.core.*` / `scripts.reports.*` with
`.wiki/` on `sys.path` (82 files carry a `sys.path.insert`, five distinct shapes); S02-T01's
layout decision must collapse both onto one. Nothing moves in S02–S05.

**Reassess after S02 (2026-10-14): B — partial changes.** S02 shipped the layout as a source
root rather than a package (exit criterion 4 was reworded in S02-T01; the slice line above
now says what shipped), grew from five to six tasks (T06: the documented invocations), and
found three things the remaining slices inherit: (1) the logging fold in S03-T04 is bigger
than "4 → 1" — 36 files call `logging.basicConfig` and six modules put their console setup
before their imports (`noqa: E402`); T04's line now carries that inventory and may split at
plan-task; (2) every `wiki index` / `wiki collect …` / entry script imports the whole
`collectors` package (~0.25 s) because registration happens on package import —
`backlog/lazy-collector-registry.md`, decided in M034 together with the collect verb;
(3) S05-T05's tree work was pulled forward: `docs/engine-layout.md` and `AGENTS.md` were
reconciled in S02-T05, so T05 re-verifies them after S03/S04 instead of rewriting. S03, S04
and S05 otherwise unchanged; S03 next.

**Reassess after S03 (2026-10-15): B — partial changes.** S03 shipped its seven tasks and
every count turned out larger than the audit's def-name tally — 25 frontmatter grammars not
17, 7 slug copies not 5, 33 + 4 + 8 logging setups not 4, 7 state writers not 3, 6
hand-typed rollup appends beside the three collectors — because the audit counted names and
the folds counted mechanisms (a smell grep per seam, a vault parity per fold, a guard that
asserts the predicate). The slice line above now says what shipped; `print` →
`core/console` left it for M034 (the Python dispatcher owns the output). Two residues are
backlog files, not tasks: `intents-seen-state-shape.md` (the one list-shaped state file)
and `backfill-voice-rollup-shape.md` (the backfill's legacy voice line). S04 and S05
unchanged: S04-T01's allowlist is AST-measured, and S05-T05 inherits the two toolchain
lessons already in KNOWLEDGE (ruff ≥ 0.16 formats Markdown fences — excluded in
`pyproject`; a formatter with an empty path variable formats the whole project). S04 next.

**Reassess after S04 (2026-10-15): B — partial changes.** S04 shipped its seven tasks,
and exit criterion 6 is met and enforced twice: a function gate with an empty allowlist
and a module-size gate whose allowlist is the doc. Its counts grew the way S03's did. The
AST found 20 long functions, not 15, and the module review split six modules, not four
(`gmeet` and `sdk_helpers` too). The slice line above says what shipped. S05 keeps its six tasks
and inherits three things. T02's type gate on `core/` now covers the `core/health/`
package (five modules) and `core/sdk_scope.py`. T05 re-verifies the S04 module lines and the
"Large modules" section in `docs/engine-layout.md`. T05's 0.7.0 release note carries S04's
one operator-visible change: a `--json` invocation prints the payload alone (S04-T06,
`960a74e`). The diagram labels that name split modules (`lint.py`'s
`check_facts_violations`, `collectors/gmeet.py` on the Drive API) still hold through the
facades; T05 re-checks them under the infographic rule. S05 next.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the
plan still fits reality. S01 lands the behaviour oracle (snapshot test) and the gates that
every later slice runs under; S02 before S03 because import paths decide where the seams are
called from; S04 after S03 so the functions being split already call the seams.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
