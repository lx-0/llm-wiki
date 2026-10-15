---
milestone: M033
slice: S05
task: T05
project: llm-wiki
closed: 2026-10-15T16:03:58+02:00
verification: passed
---

# M033-S05-T05 -- Summary

## Commits

- `3229439` -- planned
- `4e48a2d` -- release 0.7.0 + the closeout docs

This summary, the slice-plan flip and STATE follow under the same ref.

## Outcome

The engine is at **0.7.0**: `pyproject.toml`, `uv.lock` and `CHANGELOG.md [0.7.0] — 2026-10-15`
agree. The changelog states what an operator notices, each item measured from the M033
commits:

- **Fixed:** a `--json` invocation prints the payload alone. The suggestions' IMAP actions on
  Gmail accounts no longer crash. `wiki update` runs its post-pull steps from the pulled
  engine. `ingest-youtube` / `index` no longer print runpy's warning.
- **Changed:** three hyphen scripts were renamed, and the commands share one console log
  setup.
- **Added, for contributors:** the gates and the typed `--json` contract.
- **For vaults:** no config key and no migration, and schema 2 is unchanged.

The docs say what the engine is after M033:

- `docs/engine-layout.md` gains **Seams and gates**: nine seams, each with the guard test that
  refuses a second copy, then the gates (oracle, size, layout, patch surface). The intents
  handlers are now named in the tree.
- **README.** The code gates name ty and the suite's structural gates.
- **FEATURES' seam table.** Six new rows (`sdk_scope`, `entry`, `console`, `slugify`, the
  rollup line, `contracts`). The frontmatter row and the SDK-gap row were re-measured: 0
  private grammars, and `flush` now on the harness.
- **DECISIONS** closes M033 against its nine exit criteria. Criterion 9 is evidenced by
  `git log tests/golden/oracle/`: the goldens were never re-recorded after S01-T01.

The 7-file audit came out clean. README, AGENTS, `cli.md`, FEATURES, `concept.md` and
engine-layout are current (AGENTS and `cli.md` were updated in the tasks that changed them,
and `concept.md` has no M033-affected content). Both infographics are unchanged by rule: no
box names a module M033 moved, and the desktop and dev gates have no steady-state slot.

## Deviations from plan

- **The plan's `ruff check --select RUF100` is a false measurement.** It deselects the rules the
  `noqa` comments name, so all 21 look unused. The check that holds is
  `--extend-select RUF100` with the full rule set, which is clean. DECISIONS records which
  command to use.
- **The audit script found a precision gap.** The tree named the intents handlers only as
  "task / idea / note handlers"; it now lists the three file names.
- **The release path was checked beyond the plan.** On the scratch vault, `wiki update --no-skills`
  went to `4e48a2d`: the migration reported "already on the current key schema", `.wiki/` had 0
  `git status` lines after the `uv sync`, and the live `menu --json` / `doctor --json` validate
  against the contract.

## Follow-ups

- T06: the milestone close. That is the full backlog fan-out against the code (every SHIPPED
  verdict refuted first), the `PRIORITY.md` re-cut, the last-slice `reassess-roadmap`, and the
  M034 pitch re-read against what M033 left. The "Moved to M034" list in DECISIONS is that
  re-read's input.

## Verification

Plan command 1: `uv lock --check` resolves 63 packages and finds the lock current.
`version = "0.7.0"` and `## [0.7.0] — 2026-10-15` are in place. RUF100 is clean with the full
rule set, and the suite reports **2255 passed, 1 skipped**.

Plan command 2: `/tmp/t05-doc-audit.py` finds 0 modules unnamed in the tree and 0 stale names,
and all 42 paths named by the new sections exist.

CI is green on `4e48a2d` (ci + secrets-scan). The scratch vault at 0.7.0 is clean after the
update, and its payloads validate.
