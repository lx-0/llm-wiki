---
milestone: M034
slice: S01
task: T07
project: llm-wiki
closed: 2026-10-15T20:22:00+02:00
verification: passed
---

# M034-S01-T07 -- Summary

## Commits

- `13f5a73` -- M034-S01-T07 (fix): `wiki stats` — the use-llm-wiki skill ran the vault dashboard through a bare `uv run --project .wiki`, which on an iCloud vault recreates the in-vault venv; release 0.7.8
- `ff3d6a9` -- M034-S01-T07: planned — the consumer smoke on the scratch vault at S01's head, plus the defect planning found (a `wiki stats` command fixes it)

## Outcome

Every consumer of `<vault>/.wiki/wiki` works at S01's head (`13f5a73`, engine 0.7.8). The
check ran against the scratch vault with the real uv, each consumer with its own spawn shape,
via `/tmp/m034_consumer_smoke.py`: **24/24 ok**.

| Consumer | Spawn shape | Calls, all exit 0 |
| --- | --- | --- |
| Desktop app | no shell, `cwd` = vault, stdin `/dev/null`, PATH = `augmentedPath()` | `doctor --json`, `menu --json`, `collect --list --json` (JSON parsed); `compile` / `query` / `triage --help` |
| Obsidian buttons | `/bin/zsh -c "<line>"`, `cwd` = vault | `lint --structural-only` and `refresh-dashboards` verbatim; `compile` and `compile --all` with `--help`; the four `agent` lines with `--dry-run` |
| Shortcut symlink | `/tmp/m034-shortcut/wiki` → the vault's `.wiki/wiki`, run from `/tmp` | `version`, `doctor --quick --json`, `collect --list` |
| use-llm-wiki skill | `cwd` = vault | `status`, `doctor`, `doctor --json`, `doctor --quick --json`, `menu --json`, `stats`, `dedup --suggest-only` |

The LLM-costing calls are not run verbatim: `compile --progress-json`, `query … --json`, and
the agents' SDK spawns. They ran as the same dispatch with `--help` / `--dry-run`. Their
dispatch path is the one every other `py` command takes, and that path is proven above.

**The fix (`13f5a73`).** The skill and its health-check reference taught agents to run the
vault dashboard as `uv run --project .wiki python .wiki/scripts/health.py --vault .`, and so
did `health.py`'s own docstring. A bare `uv run --project .wiki` ignores
`UV_PROJECT_ENVIRONMENT`. On an iCloud vault it recreates `.wiki/.venv` inside the synced
folder: the 2026-09-17 eviction / SIGKILL class, which engine-layout's `.venv/` rule
forbids. No `wiki` command reached `health.py`.
- **`wiki stats`** (→ `health.py`, no banner, `H_STATS`) runs it from the engine's own
  environment.
- **The skill, the reference and the docstring** say `wiki stats`, and why the bare form is
  wrong.
- **Five help goldens** gained exactly the one `stats` line.
- **CHANGELOG [0.7.8]** records the fix.

## Deviations from plan

- **Unknown before the smoke:** the fix was added to the task on the defect the skill pass
  found. The plan already named it, because planning read the skill first.
- **Not fixed here: PROCESS.md.** It still teaches 12 bare `uv run --project .wiki` lines
  (the `scan_*` flags, `collectors.cli`, the dashboard modules). Several have no `wiki`
  equivalent until S06-T03's `wiki collect <name> -- <flags>`, so that task now lists them
  explicitly.
- **The Obsidian buttons ran with this shell's environment.** Neither the template nor the
  live vault configures PATH augmentation, so a GUI-launched Obsidian needs `uv` and `jq`
  from the user's shell, as before S01. `wiki` still runs `require_cmd uv` at the top.
  Nothing in S01 changed that requirement.

## Follow-ups

- **`reassess-roadmap` for S01.** All seven tasks are done.
- **S06-T03** covers PROCESS.md's bare `uv run` lines.
- **Consider in S02** (`config` + `setup`): `require_cmd uv` at the top of `wiki` now guards
  only the fallback paths and the remaining bash commands. When the bash shrinks to the
  bootstrap, it should require `uv` only when the hop needs it. Exit criterion 1 (the
  ≤ 150-line bootstrap) owns that.

## Verification

Commands, all passed:
- `python3 /tmp/m034_consumer_smoke.py /tmp/lxw-scratch`: 24/24 ok.
- `uv run --frozen pytest -q`: 2362 passed, 1 skipped. The `stats` unit test was watched
  failing first; the five help goldens were re-recorded for the one new line.

CI is green on `13f5a73` (ci + secrets-scan).
