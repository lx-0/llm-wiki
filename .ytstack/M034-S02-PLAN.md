---
milestone: M034
slice: S02
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 5
completed_tasks: 0
---

# M034-S02 -- Slice Plan

**Goal:** `wiki setup`, `wiki config …` and `wiki install-shortcut` run in Python at oracle
parity, on prompt helpers in `core/console`; `lib/config.sh` and `lib/ui.sh` are deleted.

## Tasks

- [ ] T01 -- Prompt helpers on `core/console`: confirm, ask, select_one, select_many, pause,
  next to `read_key`. Open question 3 is decided in DECISIONS (OSS candidates weighed, the
  per-vault dependency cost measured). They are line-based like `lib/ui.sh`: `read -r`
  semantics, so an answer piped on stdin is read and EOF takes the default (that is how the
  bash behaves without a TTY, and how the oracle drives the interactive commands). Prompts go
  to stderr. Unit tests drive scripted lines.
- [ ] T02 -- `config get/set/keys/path/status/edit` in the catalogue, over the existing
  `core.config` module. `edit` opens `$EDITOR` on `<vault>/.wiki/config.yaml`. Parity with the
  S01 goldens.
- [ ] T03 -- The setup wizard in Python (`wiki setup`, `wiki config setup`): the steps, the
  Ollama probe, compile-hour and URL validation, the config writes. Tests run with scripted
  answers, and one scratch run is made on a fresh vault.
- [ ] T04 -- `install-shortcut` in Python: the `~/.local/bin/wiki` symlink. A link pointing
  at another vault is replaced without a prompt, and `--print-only` writes nothing. When
  `~/.local/bin` is not on PATH, the command prints the rc line; it never edits an rc file,
  exactly as the bash does today. Parity on the fixture `HOME`.
- [ ] T05 -- `lib/config.sh` and `lib/ui.sh` are deleted along with their `wiki` call sites.
  The oracle passes, the docs naming them are updated (README, cli.md, engine-layout), and
  `wiki setup` runs end to end on a fresh scratch vault.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; no bash left for config,
setup or the shortcut.

## Notes

The wizard is the first-run experience for a new operator; keep its prompts and order unless
a difference is decided in the commit.
