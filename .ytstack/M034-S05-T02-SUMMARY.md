---
milestone: M034
slice: S05
task: T02
project: llm-wiki
closed: 2026-10-16T03:35:00+02:00
verification: passed
---

# M034-S05-T02 -- Summary

## Commits

- `b630e8f` -- M034-S05-T02: `wiki update`'s second phase runs in Python — `--post-pull <rev>` (the sync, the cloud-vault hints, both migrations, the skills sync) is scripts/update_cli.py, held to T01's 14 records unchanged; the bash phase 1 checks its flags and the checkout and hands over, as a 0.7.3 bash does after its pull; doctor and update share one hook walker (0.7.28)

The task was planned in `852a5fe`, T01's summary commit.

## Outcome

`wiki update --post-pull <rev> [--no-skills]` runs in Python, in `scripts/update_cli.py`. It
does the summary line, `uv sync`, the cloud-vault hints, both migrations (as child modules of
the engine) and the skills sync (in-process). The bash phase 1 still parses the flags and
checks the checkout. Then it hands over through `_dispatch_python`, which is what a 0.7.3
bash does after its pull. All 14 records from T01 pass unchanged.

The hook-environment check is one walker now, `core.agents.installed_wiki_commands`. It sits
behind `wiki doctor`'s `check_hooks_installed` and behind the update's warning. 0.7.27's line
grep is gone, and with it two edges, both reproduced in real bash before the CHANGELOG said
so: it missed a double-quoted hook and counted a permission rule as one. The grammar guard in
`test_agents_registry.py` now scans the bash files too; it had not seen that copy in `wiki`.

Cross-version, on scratch: a vault on the real 0.7.3 tree (`ee690a0`) updated to `b630e8f`
through its own bash. Exit 0, the config "no change", the skill linked. Its uv log shows two
syncs and no `uv run … -m migrations`, so the post-pull phase that ran was the Python one.

## Deviations from plan

- **`H_UPDATE` moved into `cli_help` now, not in T03.** The catalogue's guard wants a help
  text for every `py` command. A test holds it to the recorded heredoc
  (`update-help.txt`) until T03 switches `--help` over.
- **The routing is the bash's, after its checks.** The plan had the entry route
  `--post-pull` straight to Python. Instead `cmd_update` keeps its flag loop and the checkout
  guard, then dispatches. That keeps one help text and is literally the cross-version path.
- **Phase 2's messages carry resolved paths** (`core.paths`), as every ported command's do.
  A vault reached through a symlink shows its real path; on scratch that was `/private/tmp`
  for `/tmp`. The records, made in resolved temp paths, are unaffected.
- **RTK.md (global) got a lesson.** Inline in the Bash tool, the exit status of a grep
  pipeline gave the wrong answer about 0.7.27's grep. A script file run by real bash gave the
  right one.

## Follow-ups

- **T03 (phase 1 in Python):**
  - `test_the_python_handler_pulls_nothing_without_post_pull` goes BEFORE phase 1 lands.
    Called in-process with phase 1 there, `update_cli.main([])` would pull this checkout.
  - `cmd_update` and `lib/ui.sh` go.
  - `--help` switches to Python, held by `update-help.txt` and the `H_UPDATE` test.
  - Flush stdout before the `execv` of the pulled `wiki`.
- **Operator:** nothing new in 0.7.28.

## Verification

Commands:
- `uv run --frozen pytest tests/test_bash_oracle.py -q -k update`: 20 passed, with the 14
  records unchanged.
- `uv run --frozen pytest tests/test_wiki_update.py tests/test_agents_registry.py tests/test_health.py tests/test_cli.py -q`:
  145 passed.
  - RED first: the walker missing, the guard naming `wiki`, `update_cli` missing.
  - The five phase-2 behaviour tests passed against the bash before the port, and again on
    it.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2641 passed, 1 skipped.
- `ty check scripts/core` and ruff: clean. After the version bump, the version-sensitive
  tests passed (106).
- Scratch (`/tmp/m034-scratch-update.sh`): 0.7.3 → `b630e8f`, exit 0, Python phase 2.
- CI on `b630e8f`: both runs green.
