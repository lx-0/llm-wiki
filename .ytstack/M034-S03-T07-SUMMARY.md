---
milestone: M034
slice: S03
task: T07
project: llm-wiki
closed: 2026-10-16T00:30:00+02:00
verification: passed
---

# M034-S03-T07 -- Summary

## Commits

- `9ad0d2c` -- M034-S03-T07: lib/agents.sh, hooks.sh, skills.sh and config.sh deleted with the helpers they left without a caller; the bash layer is 1237 lines (wiki 412, common 94, seed 710, ui 21)
- `711fa3d` -- M034-S03-T07: planned + the bash recorded before it goes — 28 goldens under tests/golden/agents/, written from the bash itself

## Outcome

`lib/agents.sh`, `lib/hooks.sh`, `lib/skills.sh` and `lib/config.sh` are gone. So are the
helpers they left without a caller:
- in `ui.sh`: `select_one` / `select_many`;
- in `common.sh`: `backup_file` and the path variables and `HOOK_*` constants, each grepped
  repo-wide first.

The bash layer is 1237 lines: `wiki` 412, `common.sh` 94, `seed.sh` 710, `ui.sh` 21.

The parity tests that ran the bash now hold Python to the bash's recorded output:
- 28 goldens under `tests/golden/agents/`, recorded from the bash and pushed before the
  deletion;
- the grammar cases keep the bash probe's answers inline;
- the environment test runs end to end through the real `wiki`: a cloud vault, all four
  agents, and the exported variable lands in every hook command.

## Deviations from plan

None. The add-an-agent recipe in AGENTS.md now records the payload golden instead of
mirroring the bash.

## Follow-ups

- **S03 is complete.** Reassess the roadmap.
- **The ytstack post-commit draft names the second commit as a task's first,** for T06 and
  T07 (both first commits were planning commits). Together with T06's stale `index.lock`,
  this is worth an issue for ytstack. It is not this repo's to fix.

## Verification

Command: `uv run --frozen pytest -q` — 2505 passed, 1 skipped. The grep for the four file
names finds only history (docstrings saying "was lib/…" or "deleted in T07").

Scratch run on the fresh vault (`lib/` now holds common, seed, ui) with a sandboxed HOME:
install → status → uninstall per agent at user scope gives Claude 3, Codex 2, Gemini 3 and
Cursor 3 wiki commands, "installed", then 0 and "detected", every exit 0. Cursor at project
scope behaves the same. CI green on `9ad0d2c`.
