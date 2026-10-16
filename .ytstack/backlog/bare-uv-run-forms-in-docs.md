# The docs' remaining bare `uv run` forms (M034 S06-T05 / T06 input)

**Status:** open. Recorded 2026-10-16 (M034-S06-T04).

**Why it matters:** on a vault in iCloud Drive or `~/Library/CloudStorage` the engine's
environment lives at `~/.venvs/<vault>-wiki`, addressed through `UV_PROJECT_ENVIRONMENT`
(hard rule in `docs/engine-layout.md`). A bare `uv run` from `.wiki/` or with
`--project .wiki` does not know that. It builds `.wiki/.venv` inside the cloud folder, the
defect S01-T07 fixed in the use-llm-wiki skill and S06-T04 in `docs/PROCESS.md`.

**Where the form is still taught (grep `uv run` over `docs/ README.md AGENTS.md scripts/`):**
- Operator-facing, so the defect bites:
  - `README.md` "Running scripts manually": Option A (`cd .wiki && uv run python scripts/…`)
    and Option B (`uv run --project …`). Its "Hooks always use Option B" is also stale: the
    hook commands are `cd '<vault>/.wiki' && [UV_PROJECT_ENVIRONMENT='…' ]uv run python
    hooks/<x>.py` (`core/agents.py`).
  - `docs/cli.md` "Operator-invoked one-shot scripts (`uv run python scripts/<name>.py`)":
    `migrate_daily_to_rollup.py`, `backfill_daily_rollup.py`, `cleanup_legacy_daily_roots.py`,
    `daily_digest_runner.py`.
- Developer-facing (a checkout, rarely a cloud vault), so lower stakes:
  - `AGENTS.md` "Python environment": the by-path and module forms (its first paragraph
    already says to use `wiki …` on a cloud vault).
  - `docs/FEATURES.md` (`backfill_per_item`, `inject_daily_button`), `docs/engine-layout.md`
    (the `migrations/` line).
  - Module docstrings: `core/config.py`, `dashboard/inject_daily_button.py`,
    `migrations/*.py`, `probe_compile_scope.py`, `reports/_engine/verify_scope_lock.py`.

**Direction:** T05 cuts README and AGENTS.md anyway: replace "Running scripts manually" with
`wiki <command>` (every operator path has one) and a pointer to engine-layout's "How a
module runs", which names `<venv>/bin/python` instead of a bare `uv run`. The one-shots in
`cli.md` either get a `wiki` verb (`wiki backfill` already groups one-shot upgrades) or
the `<venv>/bin/python` form — decide in T06's docs pass. Docstrings follow whichever form
the docs settle on.
