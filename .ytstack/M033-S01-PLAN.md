---
milestone: M033
slice: S01
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 5
completed_tasks: 2
---

# M033-S01 -- Slice Plan

**Goal:** Every later refactor runs under gates: a fixture-vault snapshot test that proves the operator-facing payloads did not change, `ruff format` + `ruff check` green under an explicit policy (every ignore with a reason, 0 unused `noqa`), both enforced by pre-commit and a CI workflow that also runs the engine and desktop suites.

## Tasks

- [x] T01 -- Behaviour oracle: a shared fixture vault builder in `tests/` (deterministic: a handful of knowledge articles with frontmatter, `index.md`, `state/`, `.wiki/config.yaml`) and a snapshot test that runs `menu.main(--json)`, `doctor.main(--quick --json)` and `cli.py help` in-process, normalises volatile fields (timestamps, version, paths) and compares to committed golden files; golden files regenerated only via an explicit `--snapshot-update` flag.
- [x] T02 -- The mechanical format commit: `ruff format scripts hooks tests` (289 files) with zero logic change, suite + oracle green before and after, hash recorded in a new `.git-blame-ignore-revs`, `git config blame.ignoreRevsFile` documented in `AGENTS.md`.
- [ ] T03 -- Lint policy in `pyproject.toml`: `[tool.ruff.lint]` selecting `E,F,I,UP,B,SIM,N,RUF,PL,C90` with every ignore carrying a one-line reason (candidates measured 2026-10-14: PLC0415 991 lazy imports are deliberate in CLI dispatch; PLR2004 509; C901 + PLR091x deferred to S04's split; RUF001-003 the docs' en-dashes/arrows; E501 after format), then `ruff check --fix` for the safe fixable buckets (I001 228, UP017 95, F401 86, UP035 24, F541 22, PLR0402 21, UP037 13) and `RUF100` → 0 (295 unused `noqa` removed); suite + oracle green.
- [ ] T04 -- Hand-fixed residue until `ruff check` exits 0: PLW1510 23 (explicit `check=`), RUF059 59 (underscore the unused unpacked names), N806 32, RUF012 24 (`ClassVar` or tuple), E702 15, E402 23 as per-file ignores with the reason "sys.path bootstrap — S02 removes it"; anything that is a real defect gets its own commit + test.
- [ ] T05 -- Gates wired: `ruff` (check + format) hooks in `.pre-commit-config.yaml`; `.github/workflows/ci.yml` on push / PR to `main` running `uv sync` → `ruff check` → `ruff format --check` → `uv run pytest -q`, and in `desktop/` `npm ci` → `npm test` → `npm run lint` (node 22); README/AGENTS "how to run the gates" paragraph; the workflow seen green on `origin/main`.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- `wiki status` is implemented in the bash layer (M034's scope) — the oracle covers the Python-rendered payloads (`menu --json`, `doctor --quick --json`, `cli.py help`); `status` joins it when it moves to Python.
- The slice ends with the first CI run on `origin/main`; a red run is a defect to fix inside the slice, not a note.
