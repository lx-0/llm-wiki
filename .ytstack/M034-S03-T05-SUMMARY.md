---
milestone: M034
slice: S03
task: T05
project: llm-wiki
closed: 2026-10-16T00:20:00+02:00
verification: passed
---

# M034-S03-T05 -- Summary

## Commits

- `378e18f` -- M034-S03-T05: prompts flush stdout before they write (found on the scratch run)
- `1bfcddb` -- M034-S03-T05: wiki hooks and wiki status in Python — hooks_cli.py / status_cli.py over core/agents and core/backup, at parity with the bash oracle; setup installs in-process (release 0.7.18)
- `ac854cc` -- M034-S03-T05: oracle first — three bash cases the port changes on purpose, recorded before its first line

## Outcome

`wiki hooks install/uninstall/status` and `wiki status` run in Python (engine 0.7.18):
- **`scripts/hooks_cli.py`** runs the bash flows with lib/ui.sh's prompts on top of
  core/agents (registry, payload, merge, uninstall filter). Each write gets a core/backup
  copy and goes through a temp file. Failures are counted and exit 1.
- **`scripts/status_cli.py`** is `wiki status`.
- **`setup`** runs the hooks install in-process on its own stdin.
- **`wiki`** no longer dispatches or sources the hooks bash (539 → 481 lines).

Ten goldens pass byte-identical: install ×3, uninstall ×4, hooks status, status and
setup-with-hooks. The five decided differences are each a re-recorded golden whose diff
is exactly the change, against the bash recorded first:
- **the probe walks the hook entries** (status, `wiki status` and doctor alike);
- **unreadable configs** show their own state and get Python's parse error, with no backup;
- **the help is corrected**;
- **no jq**;
- **`wiki status <word>` is refused.**

## Deviations from plan

- **Uninstall still offers an unreadable config whose text names a hook.** With the walk
  alone, uninstall claimed "No wiki hooks installed anywhere." while the table showed it
  unreadable. Now the attempt reports it and exits 1, as the bash did.
- **`console.fail()` was added** (the bash `err`: a ✗ line on stderr). `print_error`'s
  `wiki:` prefix would have changed every failure line.
- **`H_STATUS` is new:** every `py` command needs help text.
- **Two defects were found on the way and fixed:**
  - the scratch run with `2>&1`: prompts overtook the output printed before them (`_emit`
    flushes stdout, with a RED test);
  - a golden held a path-dependent parse-error offset. The fixture now uses the
    path-free command form, and the bash record is unchanged by it.

## Follow-ups

- **S03-T07** deletes `lib/agents.sh` and `lib/hooks.sh`, with `lib/ui.sh`'s `select_*`,
  `lib/common.sh`'s `backup_file` and their dead callers. The parity tests that still
  compare with the bash (`test_agents_registry`, `test_agents_merge`, `test_hooks_merge`)
  then hold recorded expectations instead; the oracle goldens already carry the bytes.
- **`require_cmd jq` stays global** until S04 ports `seed`, its last user.
- **Recorded:** KNOWLEDGE.md ("Three byte-parity traps…") and TECH-PATTERNS (byte-counted
  `printf` padding; stderr prompts overtaking buffered stdout).

## Verification

Command: `uv run --frozen pytest tests/test_bash_oracle.py tests/test_hooks_cli.py
tests/test_agents_registry.py tests/test_health.py tests/test_setup_wizard.py -q` — passed.
Full suite: 2508 passed, 1 skipped. `ty check scripts/core` is clean.

Scratch run on the fresh vault with a sandboxed HOME and a real venv:
- status shows "detected", then install creates the config;
- `wiki status` shows "installed", and a reinstall stays idempotent (one wiki entry per
  event);
- uninstall leaves `{"hooks": {}}`. Two backups from the same second both survive, so the
  `-2` rule worked live;
- with `2>&1`, the table comes before the picker.

CI green on `378e18f`.
