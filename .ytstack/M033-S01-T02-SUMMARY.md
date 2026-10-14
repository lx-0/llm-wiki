---
milestone: M033
slice: S01
task: T02
project: llm-wiki
closed: 2026-10-14T20:10:00+02:00
verification: passed
---

# M033-S01-T02 -- Summary

## Commits

Two commits under the `M033-S01-T02:` ref — `git log --grep '^M033-S01-T02'`:
`ec061106ce52f0000c89fb767ea722b891e24490` is the mechanical format commit (290 `.py` files +
the one `pyproject.toml` line it needs); the follow-up carries `.git-blame-ignore-revs`
naming that hash, the AGENTS.md line, and this summary.

## Outcome

Every Python file under `scripts/`, `hooks/` and `tests/` is formatted by ruff (line
length 100) except one: `scripts/core/config_schema.py`, excluded in
`[tool.ruff.format]` with the reason in the config. `ruff format --check scripts hooks
tests` reports 380 files already formatted and exits 0. `.git-blame-ignore-revs` lists
the format commit with the activation command; `AGENTS.md` tells contributors to set
`blame.ignoreRevsFile` and names the gates. The full suite and the behaviour oracle are
green on the formatted tree; the oracle's goldens did not move.

## Deviations from plan

- The plan allowed for exactly this: `config_schema.py` is read as text by
  `core/config_docs.py` (field comments become `docs/config.md`), and ruff's wrapping moved
  trailing comments off the field lines — the docs-parity test showed eight descriptions
  turning into "—" and one migrating to the next key. Resolution per plan: format-only
  exclusion with a reason, the file's eleven formatter hunks reverted by targeted edits (its
  diff against HEAD is empty), no generator change in a format commit. The generator's
  fragility (a wrapped field statement loses its comment) is a follow-up.
- No RED test for a formatting commit; the gates were the suite (2030), the oracle and
  `format --check`, run before and after.

## Follow-ups

- `core/config_docs._field_comments` should survive a wrapped field statement (`name: int =
  (\n    50  # comment\n)`): read the trailing comment from the statement's last line. With
  that, the exclusion can go — S03 (seams) or S04.
- T03 enables the lint rule set; the formatter has already settled I001-adjacent whitespace,
  so the fixable buckets measured on 2026-10-14 may be smaller now.

## Verification

Command: `uv run ruff format --check scripts hooks tests && uv run pytest -q` — passed:
`380 files already formatted`, exit 0; **2030 passed, 1 skipped**. `git diff --stat
scripts/core/config_schema.py` empty after the revert. `git log -2` shows the format commit
and the follow-up; `.git-blame-ignore-revs` names `ec061106…`; `grep ignoreRevsFile
AGENTS.md` hits.
