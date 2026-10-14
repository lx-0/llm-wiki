---
milestone: M032
slice: S02
task: T01
project: llm-wiki
closed: 2026-10-14T17:50:00+02:00
verification: passed
---

# M032-S02-T01 -- Summary

## Commits

Committed together with this summary under the `M032-S02-T01:` ref — `git log --grep '^M032-S02-T01'`.

## Outcome

`scripts/core/actions.py` is the engine's action catalogue: eleven `ActionSpec` rows (id, verb,
intent group, argv, singular/plural title, tool flag), `get()`, `verb_for(argv)` (exact row →
subcommand fallback → "Run"), `tools()` (the five always-available maintenance actions under
group `tools`) and `SCHEMA = 2`. `menu_context.build_suggestions` keys each probe on a catalogue
id and emits `id` / `title` / `verb` / `group` / `argv` next to the TUI's `label`, `count`,
`priority`, `key`; the `cmd` string is gone. `wiki menu --json` returns
`{schema: 2, status, suggestions, tools}`. `menu.py` derives `dispatch_args` and the `→ wiki …`
hint from `argv`. Docs updated in the same commit (`docs/cli.md` payload block,
`skills/use-llm-wiki/SKILL.md` snippet).

## Deviations from plan

- `tests/test_menu.py` also built suggestion fixtures with `cmd` (missed by the first consumer
  grep, which only covered `scripts/`) — fixtures moved to `argv`.
- Tool titles for the two probe-backed rows (`dream-sweep`, `lint`) come from a small
  `_TOOL_TITLES` map because their counted titles make no sense without a count.

## Follow-ups

- T02 extends the same catalogue to `doctor --json` (`title` on `CheckResult`, `verb` via
  `verb_for`), and updates the doctor payload block in `docs/cli.md`.
- The desktop still reads `cmd` (`vault/menu.ts` defaults it to `''`) until T04 — the panel's
  pending rows would dispatch nothing against a schema-2 engine in the meantime; T04 lands in
  the same slice before any DMG is rebuilt.

## Verification

Command: targeted pytest (`test_actions`, `test_menu_context`, `test_cli_json_seams`,
`test_doctor`) + live `menu_context.py` payload — passed (40 passed; live payload `schema 2`,
tools `dream-sweep, lint, links-fix, dedup, review-wiki`, two live suggestions rendered with
catalogue titles). Full suite: 2023 passed / 1 skipped. TDD: `test_actions.py` failed on the
missing module and the four updated `test_menu_context` cases failed on the missing keys before
the implementation existed.
