---
milestone: M032
slice: S02
task: T02
project: llm-wiki
closed: 2026-10-14T18:25:00+02:00
verification: passed
---

# M032-S02-T02 -- Summary

## Commits

Committed together with this summary under the `M032-S02-T02:` ref — `git log --grep '^M032-S02-T02'`.

## Outcome

`CheckResult` has an optional `title` — the plain-English phrasing for GUI consumers, set next
to the check that produces the operator jargon. `to_json` always emits `title` (falls back to
`message`) and `verb` (`actions.verb_for(dispatch_args)` when the check is dispatchable, else
`null`); `wiki doctor --json` carries `schema: 2`. Thirteen check branches got titles:
setup-not-run, hooks missing, engine-update-available, stale compile-state, per-account OAuth
("Sign in to Gmail (gmail-personal)"), both wiki-on-path branches, index-drift, flush-pipeline
stalled + archived, and the three engine-cloud-eviction shapes. The TUI still renders `message`.
`docs/cli.md` documents the schema-2 doctor payload and field semantics.

## Deviations from plan

- The jargon the desktop used to regex-patch ("entity pages overdue for dream", "wikilinks")
  does not come from doctor checks at all — those were menu suggestions, covered by T01's
  catalogue titles. No doctor check needed those words.
- `title` sits last in the dataclass so positional construction in tests stays valid.

## Follow-ups

- T04 (desktop parsers) reads `title`/`verb`/`schema` and drops `friendlyHealth`.
- Checks without `dispatch_args` whose message is still operator-ish (`claude-authed`,
  `compile-errors-recent`) render their message as title; add titles when a GUI screen shows
  them prominently (S04 health tile review).

## Verification

Command: targeted pytest (`test_health`, `test_doctor`, `test_menu`, `test_cli_json_seams`) +
live `doctor.py --quick --json` — passed (87 passed; live payload `schema 2`, e.g.
`wiki-on-path | The wiki command points at another vault | Install`). Full suite: 2024 passed /
1 skipped. TDD: the extended `to_json` expectation and the new title/verb test failed before
the implementation.
