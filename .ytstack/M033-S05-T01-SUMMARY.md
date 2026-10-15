---
milestone: M033
slice: S05
task: T01
project: llm-wiki
closed: 2026-10-15T15:25:13+02:00
verification: passed
---

# M033-S05-T01 -- Summary

## Commits

- `d2e4828` -- planned (three candidates; the `typecheck` group, not `--dev`)
- `7f9049b` -- the decision: ty 0.0.88, pinned exactly, `[tool.ty.environment]`, DECISIONS
- `b80dad7` -- (fix) the dead `_credentials` import the probe found in the suggestions' IMAP
  actions

This summary, the slice-plan flip and STATE follow under the same ref.

## Outcome

ty is the engine's type checker. It is pinned at `ty==0.0.88` in a new `typecheck`
dependency group, which a bare `uv sync` does not install, so operator vaults never get it.
`[tool.ty.environment]` sets Python 3.12 and `scripts` + `hooks` as search roots.
`uv run --group typecheck ty check scripts/core` reproduces the probe: 19 diagnostics on the
35 files of `core/`, none of them an unresolved import. All of `scripts/` shows 168 (160
errors, 8 warnings).

The probe ran three ways to get a checker into pre-commit and CI on the same tree:

| | pyright 1.1.414 (PyPI wrapper) | basedpyright 1.40.2 | ty 0.0.88 |
| --- | --- | --- | --- |
| `core/` errors | 22 | 22 | 19 |
| `scripts/` errors | 212 | 212 | 161 (+ 8 warnings) |
| median wall, `core/` / `scripts/` | 2.68 s / 8.72 s | 3.02 s / 7.91 s | 0.10 s / 0.50 s |
| real findings on `core/` | 15 of 22 | 15 of 22 | 19 of 19 |
| footprint | 34 MB + Node | 73 MB + 199 MB `nodejs-wheel` | 25 MB, one binary |

Every `core/` finding was read against the code. pyright's seven false positives have two
causes. Six are a narrowing artefact (typeshed's `sys.stdin: TextIO | MaybeNone` is partly
`Any`, and pyright narrows an assignment with `Any` back to the declared `int | None`); the
isolated reproduction is in DECISIONS. The seventh is a `None` check through a boolean alias.

The probe paid off right away. On all of `scripts/` ty reported an unresolved import:
`suggestions/backends/imap.py` imported `_credentials` from the gmail adapter. That function
moved to `core/google_oauth.py` in 74f3d84 (2026-05-14), so for five months every IMAP action
on a Gmail account would have crashed with `ImportError`. A mypy-coded
`# type: ignore[import-not-found]` hid it from pyright. On a copy without the comment,
pyright's core reports "unknown import symbol". `b80dad7` adds `_credentials` to the gmail
adapter's thin-wrapper section beside `_session` / `_token_path`. The fix has tests, and the
Gmail cases were RED on the `ImportError` first.

## Deviations from plan

- **A `typecheck` group instead of `uv add --dev`.** `wiki update` and `install.sh` run a bare
  `uv sync`, and the default groups include `dev`, so the checker would have landed in every
  operator vault. This was recorded in the plan before execution.
- **Three candidates instead of two.** pyright ships on npm only. basedpyright, the same core
  packaged for PyPI, joined as the third way to install it. Its findings matched pyright's
  exactly.
- **The plan's verification command 1 cannot run again as written.** pyright and basedpyright
  were removed as the plan required, and the probe script calls their binaries. Its table is
  in DECISIONS 2026-10-15, and its raw findings are in `/tmp/t01-probe/`.
- **pyright needed a probe fix.** It ignores absolute paths in `include` ("not relative"),
  while basedpyright accepts them. The first run therefore analysed 0 files; the scope was
  then passed as a relative positional argument for both.
- **The fix commit was not in the plan.** The probe surfaced the defect, and it shipped in its
  own commit with tests, following the slice rule. It was not live-verified: a real IMAP login
  would refresh the operator's OAuth token and persist it into the live vault.

## Follow-ups

- **T02.** Make `core/` green under ty. The 19 diagnostics on `core/` share four roots: the
  `object`-typed result message and prompt in `sdk_helpers`, plus one `os.environ` passed where
  a `dict` is declared (13 together), `dataclasses.fields(type)`
  in `config_docs` (4), the `object`-typed signal-handler table in `piggyback_runner` (1), and
  `Callable.__name__` in `health` (1). After that, add the gate to pre-commit and to `ci.yml`
  (`uv sync --group typecheck`), and record the `scripts/` count (168) in KNOWLEDGE.
- **Two findings only pyright saw.** The module `__doc__` is `str | None` in
  `piggyback_runner.main`, and a hook callback does not match the SDK's `HookCallback`
  signature. T02 decides whether to fix them on their merits; the gate does not report them.
- **KNOWLEDGE.** A foreign-coded `type: ignore` silences pyright completely (added with the
  fix).

## Verification

`uv lock --check` resolves 63 packages and finds the lock current.
`uv run --group typecheck ty check scripts/core` reports **19 diagnostics** (0
`unresolved-import`). `grep -n "Type checker" .ytstack/DECISIONS.md` finds line 2103. The probe
table (verification command 1) ran before the losers were removed, with all three candidates
on both scopes (see Outcome). The suite passes with **2245 passed, 1 skipped**, and
`ruff check` reports `All checks passed!`. CI is green on `7f9049b` and `b80dad7` (ci +
secrets-scan).
