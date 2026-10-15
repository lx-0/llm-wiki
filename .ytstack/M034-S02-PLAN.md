---
milestone: M034
slice: S02
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 5
completed_tasks: 1
---

# M034-S02 -- Slice Plan

**Goal:** `wiki setup`, `wiki config …` and `wiki install-shortcut` run in Python at oracle
parity, on prompt helpers in `core/console`. `lib/config.sh` and `lib/ui.sh` shrink to what
later slices still call. Each file is deleted with its last caller: `config.sh` in S03-T04,
`ui.sh` in S05 (reassessed after S01; see T05).

## Tasks

- [x] T01 -- Prompt helpers on `core/console`: confirm, ask, select_one, select_many, pause,
  next to `read_key`. Open question 3 is decided in DECISIONS (OSS candidates weighed, the
  per-vault dependency cost measured). They are line-based like `lib/ui.sh`: `read -r`
  semantics, so an answer piped on stdin is read and EOF takes the default (that is how the
  bash behaves without a TTY, and how the oracle drives the interactive commands). Prompts go
  to stderr. Unit tests drive scripted lines.

  **They read stdin byte by byte up to the newline (`os.read(0, 1)`), never through
  `sys.stdin`** (reassessed after S01). On a pipe, `sys.stdin.readline()` buffers up to 8 KB
  ahead and swallows the answers meant for a child started after the prompt. `wiki setup`
  hands the hooks step to `wiki hooks install`, which reads its own answers from the same
  stdin, the way bash `read -r` leaves them. A test pipes two answers through a prompt and a
  child process.
- [ ] T02 -- `wiki config` in the catalogue, over the existing `core.config` module:
  - `get` / `set` / `keys` / `path`, with bash's argument checks;
  - `status` (the summary + the Ollama probe);
  - bare `wiki config`, the interactive section → key → value editor, ported on T01's
    helpers. Corrected at planning: there is no `config edit` / `$EDITOR` in the bash, the
    editor is bare `wiki config`.

  `config wizard` stays bash for this one task (T03 ports the wizard). `wiki status` calls
  `wiki config status` through the entry, so `config_cmd_status` goes now. Parity with the S01
  goldens, plus the editor and the usage errors recorded from bash first.
- [ ] T03 -- The setup wizard in Python (`wiki setup`, `wiki config setup`): the steps, the
  Ollama probe, compile-hour and URL validation, the config writes. Tests run with scripted
  answers, and one scratch run is made on a fresh vault.

  The closing "Now install hooks into agent configs?" runs `wiki hooks install` through the
  entry (a child process inheriting stdin), because hooks are bash until S03-T02. That calls
  a not-yet-ported command through its public interface, the way the menu dispatches; it is
  not a bash fallback for a ported one. S03-T02 decides whether the call becomes in-process.
- [ ] T04 -- `install-shortcut` in Python: the `~/.local/bin/wiki` symlink. A link pointing
  at another vault is replaced without a prompt, and `--print-only` writes nothing. When
  `~/.local/bin` is not on PATH, the command prints the rc line; it never edits an rc file,
  exactly as the bash does today. Parity on the fixture `HOME`.
- [ ] T05 -- The bash `cmd_config`, `cmd_setup` and `cmd_install_shortcut` are deleted with
  their case lines, and so are the `lib/config.sh` / `lib/ui.sh` functions whose last caller
  they were. That covers the wizard, `config_cmd_edit`, `config_keys`, `config_path`, the
  validators and `ask`, with the exact set re-derived by grep at the time. These stay:
  - `config_get` (with `_wiki_config_py`) for `lib/skills.sh`, and `config_cmd_status` for
    `cmd_status` — both go in S03;
  - `confirm` / `select_one` / `select_many` for `lib/hooks.sh` (S03) and `cmd_update`'s
    stash prompt (S05).

  The oracle passes, the docs naming the removed pieces are updated (README, cli.md,
  engine-layout), and `wiki setup` runs end to end on a fresh scratch vault. (Re-cut after
  S01. The old line deleted both files here, while S03's skills / hooks / status and S05's
  update still called them.)

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; no bash left for config,
setup or the shortcut.

## Notes

The wizard is the first-run experience for a new operator; keep its prompts and order unless
a difference is decided in the commit.
