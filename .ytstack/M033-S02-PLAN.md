---
milestone: M033
slice: S02
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 5
completed_tasks: 0
---

# M033-S02 -- Slice Plan

**Goal:** `scripts/` is an importable package tree with one module identity: no hyphenated entry scripts, no `sys.path.insert` outside the dispatcher's single bootstrap, handlers spawned as `python -m …`, and the tests importing the same modules the engine runs.

## Tasks

- [ ] T01 -- Layout decision proven, not argued: inventory the 68 `sys.path.insert` sites by what they insert (`SCRIPTS_DIR`, `WIKI_DIR`, a parent) and why (KNOWLEDGE C01: `core.*` vs `scripts.core.*` two identities); probe both layouts on a branch of the test suite (A: `scripts/` is the source root, top-level modules + sub-packages importable as `compile`, `core.x`, run via `python -m <mod>` with `PYTHONPATH=scripts`; B: `scripts` is itself the package, imports become `scripts.core.x`); pick by measurable cost (files touched, hook commands changed, operator-visible paths) and record in `DECISIONS.md` + `M033-CONTEXT.md` (open question 3 closed).
- [ ] T02 -- The five hyphenated entry scripts become importable modules (`ingest-html.py`, `optimize-claude-md.py`, `process-inbox.py`, `retry-failed-flushes.py`, `review-wiki.py` → underscore names or folded into the sub-package they already shim), every call site updated in the same commit (`wiki`, `lib/*.sh`, `hooks/`, `templates/`, `AGENTS.md`, `README.md`, `docs/`, `tests/test_review_wiki_failfast.py`, their own docstrings) — repo-wide grep before and after.
- [ ] T03 -- `cli.py` spawns handlers as `[sys.executable, "-m", <module>, *args]` from the chosen root (process isolation kept, `UV_PROJECT_ENVIRONMENT` / `--project` behaviour unchanged); the bash `_run_script` / `_dispatch_python` paths in `wiki` keep working byte-for-byte on the oracle (they move to Python in M034).
- [ ] T04 -- The `sys.path.insert` sites go: modules import from the package root; the one remaining bootstrap lives where the decision put it (dispatcher / `conftest.py`); E402 per-file ignores from S01-T04 removed; `pythonpath` in `[tool.pytest.ini_options]` matches the layout; KNOWLEDGE C01 marked closed with the proof (one `id()` for `core.config` under pytest).
- [ ] T05 -- Operator path proven: `wiki update` + `uv sync` on a scratch copy of a vault's `.wiki/` (hook commands, piggyback spawn lines, `install.sh`) still resolve every entry point; `docs/engine-layout.md` + `AGENTS.md` tree updated; `wiki doctor` unchanged on the oracle.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- Renaming the package to `llm_wiki` is explicitly out (it would change every operator hook command — that is M034's bash port). T01 chooses between the two layouts that keep the directory name.
