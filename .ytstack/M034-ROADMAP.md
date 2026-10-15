---
milestone: M034
project: llm-wiki
size: L
created: 2026-10-15T18:13:20+02:00
status: planned
total_slices: 6
completed_slices: 1
---

# M034 Roadmap

**Goal:** `wiki` is a thin bash bootstrap that hands every command, in one hop, to one Python
dispatcher. One command table sits behind both `wiki help` and the home menu, and the README,
AGENTS.md and the TUI carry only what their readers use.

**Exit criteria:** see `M034-CONTEXT.md`. Nine items:
1. `wiki` ≤ 150 lines and `lib/*.sh` gone;
2. one hop, with no `uv run` per call;
3. behaviour held by an oracle recorded before each port;
4. one table behind help and menu;
5. command output through `core/console`, with a `print(` gate;
6. a lazy collector registry and one collect verb;
7. README ≤ 300 lines and AGENTS.md ≤ 250;
8. the operator path proven on scratch (update, setup, the desktop app, the Obsidian buttons,
   the shortcut);
9. engine 0.8.0 and the backlog reconciled.

## Slices

Slice detail lives in per-slice `M034-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

Suggested framing (refine in slice-milestone; the starting point is measured in CONTEXT). The
size is L with six slices; the template's floor of four is too few for 2,885 lines of bash
and three tables.

- [x] S01 -- **Oracle + bootstrap** (7 tasks; re-cut after T04, see the slice plan's notes).
  - Extend the oracle to the bash commands' observable behaviour (fixture vault + fixture
    `HOME`), recorded from the bash version.
  - The thin `wiki`: symlink resolution, vault guard, venv resolution, `exec` of the venv
    Python into `cli.py`.
  - Port the thin wrappers into the catalogue: menu, doctor, version, help, dream and
    dream-entity routing, the OAuth aliases (`status` moved to S03, where its second bash
    library is ported).
  - Decide open questions 1 and 2.
- [ ] S02 -- **Config + setup** (5 tasks). Prompt helpers on `core/console`, the setup
  wizard, `config get/set/edit/status`, `install-shortcut` (symlink + rc line, with backups).
  `lib/config.sh` and `lib/ui.sh` shrink to what later slices still call, and each file
  retires with its last caller (reassessed after S01):
  - `config_get` stays for `lib/skills.sh` and `config_cmd_status` for `cmd_status` → S03;
  - `confirm` / `select_*` stay for `lib/hooks.sh` (S03) and update's stash prompt (S05).
- [ ] S03 -- **Hooks + skills** (4 tasks). The agent registry, the per-agent payloads and
  the JSON merges into agent configs (hook commands byte-identical), `skills
  install/uninstall/sync/status`, and `wiki status`. `lib/agents.sh`, `lib/hooks.sh`,
  `lib/skills.sh` and `lib/config.sh` retire.
- [ ] S04 -- **Seed** (4 tasks). The template seeding with its overlay, plugin, env,
  meta-bind and dashboard-button merges, at parity on the fixture vault and a copy of the live
  `.obsidian/`; `lib/seed.sh` retires.
- [ ] S05 -- **Update + the last bash** (5 tasks). `update` with the post-pull re-exec of
  the pulled engine, proven 0.7.3 → M034 on a scratch clone. `lib/common.sh` and `lib/ui.sh`
  retire, and `wiki` lands at ≤ 150 lines. One help system: the bash help texts move into
  `cli_help` (`cmd_help` went in S01-T05).
- [ ] S06 -- **Surface diet + close** (6 tasks).
  - One table behind help and menu; `print` → `core/console` with its gate; the lazy
    collector registry and the collect verb.
  - README ≤ 300 and AGENTS.md ≤ 250; the TUI cosmetics.
  - CHANGELOG 0.8.0 and the backlog reconcile.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks whether the
plan still fits reality. S01 lands the oracle that every port is measured against, and the
bootstrap the ported commands run behind. S02–S04 port the commands with no self-update risk.
S05 ports `update` last: it is the path that has to work across the old and the new engine,
and it removes the last bash. S06 cuts the surfaces once all commands live in one place.

## How to update this file

- Flip a slice checkbox `[ ]` → `[x]` when all of its tasks are confirmed by `summarize-task`.
- Update the `completed_slices` count.
- On milestone completion, flip `status: planned` → `status: done` and update STATE.
