---
milestone: M033
slice: S02
task: T04
project: llm-wiki
closed: 2026-10-14T20:15:00+02:00
verification: passed
---

# M033-S02-T04 -- Summary

## Commits

Two commits under the `M033-S02-T04` ref — `git log --grep '^M033-S02-T04'`: A (`50bc825`, the
import rewrite + the layout guard) and B (committed together with this summary: the bootstrap
deletions, `hooks/_bootstrap.py`, pytest `pythonpath`, the re-derived E402 ignores).

## Outcome

One import identity, one bootstrap. `scripts.core.*` / `scripts.reports.*` are spelled nowhere
under `scripts/ hooks/ tests/` any more (28 files / 75 lines rewritten onto `core.*` /
`reports.*`, one of them a quoted `monkeypatch.setattr` target that had been patching the other
identity). Every per-module `sys.path.insert` is gone — 83 lines across 80 files (8 in A, 75 in
B) together with the `sys` / `Path` imports that only served them. `hooks/_bootstrap.py` is the
one bootstrap left, imported first by `pre-compact.py` and `session-end.py`: the two hooks are
the only engine code the harness runs as plain scripts; everything else is `python -m` through
`core.entry` since T03, or pytest with `pythonpath = ["scripts", "hooks"]`. `tests/test_layout.py`
guards all of it — no second spelling (imports and quoted dotted strings), no `sys.path.insert`
outside the allowlist, no `scripts/__init__.py`, `core.config` resolved from
`core.entry.SCRIPTS_DIR`. `wiki config` (`lib/config.sh`) runs `python -m core.config`;
`WIKI_CONFIG_PY` left `lib/common.sh`. The E402 per-file ignores are re-derived from what ruff
reports with the bootstraps gone: `flush.py` (env sanitising before the SDK import), `lint.py` +
`tests/test_sdk_helpers.py` (section-local imports), `hooks/*.py` (bootstrap first);
`reconcile.py`, `health_trends.py`, `conftest.py` dropped. Migration / generator docstrings and
the `config_docs` staleness hint spell the `-m` form. `docs/engine-layout.md` lists the
bootstrap; KNOWLEDGE C01 carries its closure note.

## Deviations from plan

- The bootstrap lives in `hooks/`, not in the dispatcher / `conftest.py` the task line named:
  pytest's `pythonpath` already covers conftest, `cli.py` stopped needing one with T03's `-m`
  spawn, and only the hooks run as plain scripts.
- C01 is closed by a textual guard rather than an `id()` probe. `scripts.core` stays importable
  as an implicit namespace package whenever `.wiki/` is on `sys.path` (`python -m pytest` puts
  the cwd there), so `core.paths is scripts.core.paths` still answers False in that setup —
  re-run for the record. Identity is kept out of the code by spelling, not by a runtime check.
- The rewrite's Edit lost the trailing space of `"from "` → `fromcore.*` in 25 files (173
  syntax errors at collection); repaired with a second `replace_all`, lesson in KNOWLEDGE.
- The F401 / I001 cleanup ran as `--fix --select F401,I001,RUF100`; RUF100 deleted 33 `noqa`
  directives for rules outside the selection (the S01-T03 lesson, re-tripped under `--fix`).
  All restored from the diff with their original reason text; the KNOWLEDGE entry gained the
  recovery recipe. `tests/test_memory_resolver.py` lost its E402 for real (constant moved
  below the import block).
- `lib/config.sh` / `lib/common.sh` were not in the plan's file list: `_wiki_config_py` spawned
  `scripts/core/config.py` by path, which the bootstrap removal would have broken.
- The future-dated ytstack stamps from the earlier date slip (16 plan / summary files from
  M032-S04-T02 to this task's plan, all `2026-10-15Txx` while the day was 2026-10-14) are
  corrected from the commit log in the follow-up commit (plan `created` = the previous task's
  commit time, summary `closed` = the task's own commit); STATE `last_updated` in this one.

## Follow-ups

- T05: operator path on a scratch vault copy (`wiki update` / `uv sync` / hook commands /
  piggyback spawn lines / `install.sh`), `docs/engine-layout.md` + `AGENTS.md` trees, doctor
  unchanged on the oracle.
- The console-before-import pattern now visible as inline `noqa: E402` in `review_wiki.py`,
  `optimize_claude_md.py`, `query.py`, `menu.py`, `compile.py`, `scan_screenshots.py` (and
  `logging.basicConfig` in the first two) is S03 seam material — a shared console setup that
  imports cleanly — not T04's.
- The Edit-tool trailing-whitespace lesson is cross-project tool knowledge: candidate for the
  global TECH-PATTERNS at wrapup.

## Verification

Command: `uv run pytest tests/test_layout.py -q && uv run pytest -q 2>&1 | tail -1 && uv run
--group lint ruff check scripts hooks tests` → guard **4 passed** (RED first: the
`sys.path.insert` half was red after A until B landed), suite **2048 passed, 1 skipped**
(21 s), `All checks passed!`; `ruff format --check` → 385 files already formatted;
`grep -rn "sys.path.insert" scripts hooks tests --include='*.py'` → `hooks/_bootstrap.py` only
(besides the guard's own assertion text and the child-process driver string in
`test_piggyback_runner.py`, which the line-anchored regex ignores by design); dispatcher smokes
`preprocess --list`, `collect --list`, `process-inbox --help`, `ingest-html --help`,
`review-wiki --dry-run` → all dispatch through `python -m`; hook import chain with `hooks/` as
cwd (`_bootstrap` → `_transcript` → `core.flush_pipeline`, `core.config.__file__` under the
engine's `scripts/`) → ok; `PYTHONPATH=scripts uv run python -m core.config get
models.compile_model` → `claude-opus-4-8`; `bash -n lib/config.sh lib/common.sh wiki` → ok. CI on
`origin/main` after the push: recorded in STATE.
