---
milestone: M034
slice: S02
task: T02
project: llm-wiki
closed: 2026-10-15T20:52:00+02:00
verification: passed
---

# M034-S02-T02 -- Summary

## Commits

- `2a612a5` -- M034-S02-T02: `wiki config` in Python — config_cli.py over core.config (get / set / keys / path with the bash's argument checks, status with the Ollama probe, the bare-`wiki config` interactive editor on core/console's prompts); release 0.7.9
- `8f44ea4` -- M034-S02-T02: the bash oracle records six more `wiki config` paths from the bash, before the port (60 cases)
- `5554b19` -- M034-S02-T02: planned — wiki config as one Python handler; config wizard stays bash for this one task; corrected at planning: no `config edit` / $EDITOR

## Outcome

`wiki config` is a catalogue command with one handler, `scripts/config_cli.py`, built over
`core.config`.
- **`get` / `set` / `keys` / `path`** run `core.config`'s own CLI (`_cli(argv)`), with the
  bash's argument-count checks in front.
- **`status`** prints the summary rows and probes Ollama on `httpx`, under curl's contract:
  `GET {url}/api/tags`, 3 s, 2xx.
- **Bare `wiki config`** is the interactive section → key → value editor, on T01's
  `core/console` prompts. It reads values afresh after each write, through `core.config`'s new
  public `value_of()` / `keys()` over `load()`.
- **`core/console.print_error`** is now the one `wiki:` / red-✗ error line, and the dispatcher
  uses it too.

Bash side:
- **`wiki`** lost `cmd_config` and `help_config`. `config)` is one transitional line: `wizard`
  → the bash wizard until T03, everything else → the one hop. `cmd_status` calls
  `wiki config status` through the entry.
- **`lib/config.sh`** lost `config_cmd_edit`, `config_cmd_status` and `config_keys`. What is
  left serves the wizard and `lib/skills.sh`'s `config_get`; 130 lines remain, and `wiki` is
  down to 642.

Live on the scratch vault:
- `config status` reaches the real Ollama (`✓ Ollama reachable`);
- `wiki status` prints identically through the entry;
- `get`, a piped editor session and the usage error behave as recorded.

## Deviations from plan

- **The oracle-first commit was skipped, then restored.** The six new cases were recorded from
  the bash before the port, but not committed before porting. Three of them were then
  overwritten with the port's output. The bash versions were regenerated in a scratch
  worktree at the pre-port commit `5554b19` and committed alone as `8f44ea4`. The port
  (`2a612a5`) moves only the decided lines; the diff was read before re-recording.
- **The plan's comment correction was dropped.** The planned "programmatic writes keep
  comments" correction was wrong, and the recording proved it: `_set_in_yaml` re-dumps the
  file under a fixed header, and the oracle shows the fixture's comment line replaced. The help
  line stays. It is filed as `backlog/config-set-keeps-comments.md` (a line-level writeback),
  in PRIORITY.md's Low tier.
- **One stale help example was corrected:** `claude-opus-4-7` → `claude-opus-4-8`, today's
  default.

## Follow-ups

- **T03 ports the wizard.** It removes the transitional `config)` line, `config_cmd_setup_wizard`
  and its validators. `cmd_setup`'s hooks step dispatches `wiki hooks install` through the
  entry.
- **`backlog/config-set-keeps-comments.md`** is filed.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_config_cli.py tests/test_bash_oracle.py -q`. The 11
  config tests were watched failing first. The oracle has 60 cases, and only the decided lines
  moved: the error prefix, the editor's two prompts on stderr, and two help lines.
- `uv run --frozen --group typecheck ty check scripts/core`: clean.
- `uv run --frozen pytest -q`: 2406 passed, 1 skipped.

CI is green on `2a612a5` (ci + secrets-scan).
