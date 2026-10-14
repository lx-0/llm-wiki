---
milestone: M033
slice: S01
task: T03
project: llm-wiki
closed: 2026-10-14T20:50:00+02:00
verification: passed
---

# M033-S01-T03 -- Summary

## Commits

Committed together with this summary under the `M033-S01-T03:` ref — `git log --grep '^M033-S01-T03'`.

## Outcome

`pyproject.toml` carries the lint policy: `[tool.ruff.lint]` selects
`E, F, I, UP, B, SIM, N, RUF, PL, C90`; every ignore names its reason in the config —
PLC0415 (lazy imports are the engine's pattern), PLR2004 (the real thresholds are config
knobs), E501 (the formatter owns line length), RUF001–003 (typography, not typos), and the
complexity family C901 / PLR0911 / PLR0912 / PLR0913 / PLR0915 / PLR0917 (S04 gates length
with a committed test; thresholds revisited at its close). `per-file-ignores`: F401 in
`__init__.py` (re-exports) and E402 in the six files that still have code before imports
(listed by file, not by rule, until S02 removes the bootstraps). `[tool.ruff] src =
["scripts", "tests"]` makes the import sorter file `core`, `collectors`, … as first-party.
One `ruff check --fix` pass (safe fixes only) touched 230 files: imports sorted, unused
`noqa` removed (RUF100 absent under the project config), unused imports and import-names
dropped, `timezone.utc` → `datetime.UTC`, deprecated `typing` imports modernised,
placeholder-less f-strings and `import a.b as b` forms cleaned; `ruff format` after it. The
three registries whose import order is their run / listing order — `producers`,
`collectors`, `preprocessors` — keep that order inside `# isort: off` / `# isort: on`
blocks, verified against HEAD by importing each package and printing `all_*()` names. What
remains for T04: 244 findings across 41 codes (RUF059 59, N806 32, RUF012 24, PLW1510 23,
E741 10, SIM105 9, PLW2901 8, F841 7, RUF015 6, SIM117 / RUF046 / RUF005 5 each, SIM115 4,
the rest ≤ 3).

## Deviations from plan

- The first autofix run broke 4 tests + 5 fixture errors — two root causes, both the
  autofix exposing something that was already wrong:
  1. `compile.py` imported `load_state` and never used it; four tests monkeypatched
     `compile.load_state` — a patch on a name the module never reads, i.e. a dead patch that
     had been lying about isolating state. F401 removed the import, the patches raised
     `AttributeError`, the patches are gone (the tests still pass: they never depended on it).
  2. The import sorter alphabetised the side-effect blocks in `producers/__init__.py`
     (run order suggestions → curiosity → takes → folder_curiosity → intents, asserted by
     `test_package_import_registers_all_three`), `collectors/__init__.py` (the order
     `wiki collect --list` and piggyback discovery report) and `preprocessors/__init__.py`.
     Restored by hand under `# isort: off` — which ruff honours only when the action comment
     stands alone on its line; the first attempt with a trailing explanation was silently
     re-sorted.
- Verification pitfall worth the note: `ruff check --select RUF100` alone reports every
  `noqa` whose rule is not in that one-rule selection as unused (34 here); RUF100 is read
  from the statistics under the project config, where it is absent. The plan's command was
  corrected.
- No RED test: the task is config + mechanical fixes; the gates were the suite (2030), the
  behaviour oracle and `ruff format --check`, run after each pass, plus a review of every
  import the fix removed (139 statements flagged by a diff script, all either moves,
  renames by UP017 / UP035 / PLR0402, or genuinely unused names — no consumer found for any).

## Follow-ups

- T04: the 244-finding residue, hand-fixed or ignored with a reason, until `ruff check`
  exits 0; E402 per-file-ignores retire with S02's bootstrap removal.
- KNOWLEDGE (same commit): three bullets under a new "Engine toolchain (M033)" heading —
  isort action comments, the RUF100 selection pitfall, dead monkeypatch targets surfacing
  through F401.

## Verification

Command: `uv run ruff check scripts hooks tests --statistics` (no RUF100 / I001 / F401 /
UP017 / UP035 / F541 / PLR0402 / UP037 among the 41 codes), `uv run ruff format --check
scripts hooks tests` (`380 files already formatted`), `uv run pytest -q` — passed: **2030
passed, 1 skipped**. Registration orders printed from the three packages equal the import
order in the HEAD files.
