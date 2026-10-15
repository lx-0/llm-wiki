---
milestone: M034
slice: S02
task: T03
project: llm-wiki
closed: 2026-10-15T21:20:00+02:00
verification: passed
---

# M034-S02-T03 -- Summary

## Commits

- `bf6064f` -- M034-S02-T03 (fix): a failed `uv sync` in the one hop says so (an asdf uv under a foreign HOME exited 126 in silence)
- `5caf5a6` -- M034-S02-T03: the setup wizard in Python — `wiki config wizard` (config_cli.wizard) and `wiki setup` (setup_cli: the wizard, then the hooks step as a child reading the rest of stdin); release 0.7.12
- `efc56ae` -- M034-S02-T03 (fix): features.procmail_execution gates the All-Inkl procmail write — it had no reader since the first public release; default stays on; release 0.7.11
- `d86a411` -- M034-S02-T03 (fix): the setup wizard wrote its own validation warning into config.yaml; the bash oracle records the wizard's paths, fixed first; release 0.7.10
- `55ab6d7` -- M034-S02-T03: planned

## Outcome

`wiki setup` and `wiki config wizard` run in Python.
- **`config_cli.wizard`** asks the six questions with the bash's texts, defaults and
  validators. It shares the Ollama probe with `config status`, and writes through
  `core.config`'s `set`.
- **`setup_cli`** runs the wizard, then "Now install hooks into agent configs?". Yes runs
  `<.wiki>/wiki hooks install` as a child that inherits stdin; its exit code is setup's.
- **The pipe case held.** In the oracle's `setup-with-hooks`, the hooks installer reads its
  own answers from the same piped stdin after the Python prompts. The HOME change
  (`~/.claude/settings.json` with the hooks) is identical to the bash recording, which is
  T01's byte-wise reading working end to end.

The bash side shrank:
- **`wiki`** lost `cmd_setup`, `help_setup` and the `setup)` / transitional `config)` lines,
  and is down to 606.
- **`lib/config.sh`** keeps only `config_get` / `config_set` (20 lines) for `wiki skills`
  until S03.
- **`lib/ui.sh`** lost `ask` (the wizard was its last caller) and `pause` (dead).

**Three defects were found and fixed,** each in its own commit:
1. **The bash wizard wrote its own warning into config.yaml** (0.7.10). Its validators warned
   on stdout inside `$(ask …)`, so a refused URL became
   `models.ollama_url = '! Must start with http:// or https://\n<url>'`, and a refused hour
   aborted the wizard. The recording caught it, and the fix landed in the bash before the
   port. The live vault was not affected (checked read-only).
2. **`features.procmail_execution` had never had a reader** (0.7.11). Repo-wide grep plus
   `git log -S` back to the first public release: the wizard asked it and status showed it,
   but `AllInklProcmailFilter.apply` wrote server-side rules regardless. It is now a real
   gate for non-dry-run writes; the default stays `True` (lxw sets it true). The "off by
   default" texts were wrong and are corrected. DECISIONS 2026-10-15.
3. **A failed `uv sync` in the one hop was silent** (0.7.12). An asdf-shimmed uv under a
   foreign HOME exits 126 and prints nothing. `wiki` now says so and names the command, with
   `UV_PROJECT_ENVIRONMENT` set, so following the hint never recreates an in-vault venv.

Live on the scratch vault, `wiki setup` with a sandboxed HOME, all defaults and hooks "no",
exits 0 and asks all six questions. The sandbox HOME stays empty. The stamp first had to be
refreshed with the real HOME; that is defect 3's trigger.

## Deviations from plan

- **The wizard lives in `config_cli.py`, not in a new `setup_wizard.py`.** It is `wiki config
  wizard`'s, and shares the output helpers and the store seams; `setup_cli.py` is the thin
  `wiki setup` on top.
- **Two fixes were not in the plan:**
  - the validators' stdout capture (found recording the bash);
  - the silent `uv sync` (found by the scratch run).
- **The oracle-first rule held this time.** `d86a411` was pushed before any port code.

## Follow-ups

- **T04:** `install-shortcut` in Python.
- **T05:** the slice's cleanup. `cmd_config` / `cmd_setup` and the wizard's library pieces
  are already gone; what remains is `install-shortcut`'s bash and the docs pass named in the
  slice plan.
- **S03-T02:** `wiki setup`'s hooks step may become in-process once hooks are Python.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_setup_wizard.py tests/test_config_cli.py tests/test_bash_oracle.py -q`.
  The wizard tests (7), the procmail gate tests (2) and the failing-sync hop test were each
  watched failing first. In the oracle (62 cases) only the decided lines moved: the yes/no
  prompts on stderr, no "Default OFF.", and the six questions in `setup --help`.
- `uv run --frozen pytest -q`: 2418 passed, 1 skipped.

CI is green on `d86a411`, `efc56ae` and `bf6064f` (ci + secrets-scan each).
