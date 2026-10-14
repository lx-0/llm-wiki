---
milestone: M033
slice: S01
task: T05
project: llm-wiki
closed: 2026-10-14T22:40:00+02:00
verification: passed
---

# M033-S01-T05 -- Summary

## Commits

Three commits under the `M033-S01-T05:` ref — `git log --grep '^M033-S01-T05'`: `6cc4f0b`
(the gates), `985a620` (the first CI run's one red test + action bumps), and the closeout
commit carrying this summary.

## Outcome

`.github/workflows/ci.yml` runs on every push and PR to `main`: the `engine` job
(`astral-sh/setup-uv`, Python 3.12, `uv sync --frozen --group lint`, `ruff check`,
`ruff format --check`, `pytest -q`) and the `desktop` job (node 22, `npm ci`, `npm test` =
tsc + svelte-check + vitest, Biome). Run `38604746805` on `985a620` is green: engine 34 s,
desktop 27 s — the first time this repository's 2030 tests ran anywhere but the dev Mac.
`.pre-commit-config.yaml` gained `astral-sh/ruff-pre-commit` v0.16.10 (`ruff-check --fix`,
`ruff-format`) scoped to `scripts/ hooks/ tests/` with `config_schema.py` excluded from the
format hook; `pre-commit run --all-files` is green locally (gitleaks skipped there — its
hook builds from Go source; CI runs it). `pyproject.toml` has a `lint` dependency group
pinning `ruff==0.16.10` (ruff came from Homebrew before; CI and clones take it from the lock,
operator vaults' plain `uv sync` does not pull it) and `force-exclude = true`. README's
"Security and code gates" and AGENTS.md's Python style line say how to run all of it.

## Deviations from plan

- **The first CI run found one macOS assumption in the suite**, exactly what the task
  exists for: `test_render_index_always_full_tree` asserted a `created` date in a rendered
  file line; the renderer documents that `created` (`st_birthtime`) is omitted where the
  platform has none, and Linux has none. The test now asserts the platform's branch.
- `pre-commit run --all-files` also exercised the pre-existing `end-of-file-fixer` hook
  over the whole tree for the first time: it trimmed the trailing blank lines of the four
  vault templates (`templates/Templates/TPL *.md` — Obsidian inserts those verbatim, the
  blank lines are the template's shape) and added a final newline to the Excalidraw JSON
  and the seeded `.obsidian` JSON. Templates and `.obsidian` JSON restored byte-for-byte
  (verified against HEAD), the hook now excludes `templates/` and `docs/*.excalidraw`; the
  harmless newline fixes on `.gitignore`, five backlog notes and `docs/vault-concept.excalidraw`
  (a 67 KB single-line file the Read tool cannot open) were committed.
- `actions/checkout` and `actions/setup-node` moved from v4 to v5: the first run annotated
  the v4 majors as targeting the deprecated Node 20 runtime.
- The plan's "ruff hooks run ruff from the hook env, independent of uv's ruff" holds; both
  pins are the same number and the config says they move together.

## Follow-ups

- S02 retires the six E402 per-file ignores with the `sys.path` bootstraps.
- `ubuntu-latest` migrates to Ubuntu 26 on 2026-10-19 (runner annotation); nothing in the
  jobs depends on the image version, but the first run after the switch is worth a look.
- KNOWLEDGE (same commit): explicit-path tools vs `exclude`; the EOF hook vs vault
  templates; platform-conditional assertions.

## Verification

Command: `SKIP=gitleaks uvx pre-commit run --all-files` (exit 0, every hook Passed or
Skipped) and `gh run watch 38604746805 --exit-status` — passed: `✓ main ci`, engine
(ruff + pytest) 34 s, desktop (typecheck + vitest + biome) 27 s, on `985a620` =
`origin/main`. Locally: `uv run --group lint ruff check scripts hooks tests` → `All checks
passed!`, `ruff format --check` → 380 files already formatted.
