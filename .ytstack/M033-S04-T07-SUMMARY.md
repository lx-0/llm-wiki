---
milestone: M033
slice: S04
task: T07
project: llm-wiki
closed: 2026-10-15T15:05:50+02:00
verification: passed
---

# M033-S04-T07 -- Summary

## Commits

- `4c5f2d9` -- planned (four green groups; the patch-surface rule)
- `259f243` -- (A) `core/health.py` → the `core/health/` package
- `be1142c` -- (B) `lint.py` → checks vs reporting
- `2971952` -- (C) `cli.py` → catalogue vs dispatch
- `c43481d` -- (D1) the path-scope gate → `core/sdk_scope.py`
- `8b5842b` -- (D2) the Drive client → `adapters/drive/google.py`
- `2deb438` -- (docs) 13 stale `collectors/calendar.py` references
- `3c52179` -- (D3a) dream's dead `_is_substrate_file` + `_SUBSTRATE_ROOTS`
- `2bacfc2` -- (D3b) `dream.py` → `dream_model` / `dream_corpus` / `dream_priority`
- `8ec0767` -- (D4) the module-size gate + the "Large modules" reasons

This summary, the slice-plan flip and STATE follow under the same ref
(`git log --grep '^M033-S04-T07'`).

## Outcome

The god modules are split where it pays, and two gates keep them that way. No function under
`scripts/` reaches 150 lines (0 of 1,503; the function gate's ALLOWLIST is empty). No module
passes 1,000 lines unless `docs/engine-layout.md` § "Large modules" states why it stays one
module, and that list holds four entries.

| module (before) | after |
| --- | --- |
| `core/health.py` (1,755) | `core/health/`: `__init__` 152 · `_base` 60 · `environment` 593 · `engine` 444 · `pipeline` 636 |
| `lint.py` (1,452) | `lint` 347 · `lint_model` 187 · `lint_checks` 817 · `lint_schema` 183 |
| `cli.py` (1,300) | `cli` 258 · `cli_help` 610 · `cli_catalog` 491 |
| `core/sdk_helpers.py` (1,166) | `sdk_helpers` 981 · `sdk_scope` 195 |
| `collectors/gmeet.py` (1,322) | `gmeet` 1,172 · `adapters/drive/google` 175 |
| `dream.py` (2,182) | `dream` 1,224 · `dream_model` 107 · `dream_corpus` 680 · `dream_priority` 214 |

The four reasons on record: `core/config_schema.py` is the hand-formatted knob table that
`core/config_docs.py` reads as source text. `dream.py` is the `__main__` pipeline once its
model, corpus and priority layers left. In `collectors/gmeet.py` the pairing rules and the file
shape they define change together. `migrations/migrate_config_keys.py` is the one legal config
write path, and the CLAUDE.md hard rule names it by path. `tests/test_module_size.py` holds
the list to the doc. A module over the limit without an entry fails, an entry under the limit
fails (shrink-only), and so does a reason under six words.

Every move is pure. AST comparison finds every top-level name identical (docstrings included)
or renamed on purpose. The parity dumps match before and after, and so do the oracle goldens.
The patch-surface rule held throughout: a split module binds none of the names tests patch, so
a stale patch raises instead of silently isolating nothing. `core.health` binds none of its 13
patched names. `lint` re-exports nothing patched. The gmeet tests' `_DriveClient` patch raised
on all 15 sites until it moved. Where the old module keeps a legitimate binding (`dream.py`
still reads `ROOT_DIR`), a stale patch cannot raise. There `tests/test_dream_layout.py` scans
the tests instead: every direct `setattr` on a dream module must name a single binder, otherwise
it goes through `tests/_dream_paths.py:patch_dream_path`. Its first RED run listed 22 sites. Four
of them were `test_web_research`'s `raising=False` patches, which had become silent no-ops on a
module that no longer bound the name.

## Deviations from plan

- Group D shipped as six green commits instead of one: D1, D2, the docs fix, D3a, D3b and D4.
- D2 renamed the client to `GoogleDriveClient` / `DriveAPIError`, mirroring the calendar
  adapter, instead of keeping both gmeet names bound. The class name is not observable. Every
  `GmeetAPIError` is caught inside the collector and logged by message only. The client also
  gained `get_file(file_id, fields=…)`, because gmeet's email discovery had reached into the
  private `_get` with the base URL. That was the only non-move change, and parity shows the
  same requests. The adapters package docstring listed only `mailbox/`, so it was rewritten.
- The calendar-path fix (`2deb438`) was not planned. The stdlib-shadow rename to
  `calendar_collector.py` had left 13 references to a file that does not exist. `docs/config.md`
  was regenerated from the two schema comments.
- D3a was not planned. `_is_substrate_file` never had a caller since M014 (repo-wide grep plus
  `git log -S`), so it and `_SUBSTRATE_ROOTS` went out in their own commit. The fixtures' patches
  of `RAW_DIR`, `DAILY_DIR` and `_SUBSTRATE_ROOTS` had been no-ops and went with it.
- D3b needed a base module the plan did not name. `dream_model.py` holds `EntityRef`, the kind
  table and the cooldown. Without it the corpus and priority modules would import `dream.py`,
  which is a circular import, and a double import when `wiki dream` runs it as `__main__`. The
  orphan Opus-pricing comment was dropped, since no cost-estimate code stood behind it.
  `test_dream_sampling`'s fixture now isolates the backoff store too; it used to point at the
  engine's real `state/` path.
- The scope tests moved with the code (`git mv` to `tests/test_sdk_scope.py`).
- `tests/test_function_length.py`'s config_schema note said 72 % comment. Measured, it is 75 %,
  and the note now says ~75 %.
- AGENTS.md § Style gained the two size gates. Neither was documented for agents before.
- `dream.py` (1,224) and `collectors/gmeet.py` (1,172) stay over the limit with a reason. The
  plan expected that outcome.
- Parity a and b had to be re-based. The dream E2E seeded two entities, three raw notes and a
  digest into the scratch vault. The old code (worktree at `4c5f2d9`) run on today's scratch
  vault is identical to the new code. The scratch vault keeps the seed, so later baselines are
  taken on that state.

## Follow-ups

- None new for the backlog. The dream E2E's `t07d-dream-e2e.sh` pattern (seed the scratch
  vault, run the CLI as `__main__`, diff) is reusable for the next dream change.
- KNOWLEDGE: the "Splitting a module" entry now covers the case the A-guard cannot catch, plus
  the `raising=False` trap.
- M034 keeps `print → core/console`; T05's `collector-loop-quirks.md` is unchanged.

## Verification

Plan command 1: the targeted set reports `195 passed`. `uv run pytest -q` reports **2242
passed, 1 skipped**. `ruff check` reports `All checks passed!`.

Plan command 2: `# total >= 150: 0 of 1503 functions`.

Plan command 3 (parity): c and d are identical as run. a and b are identical once both sides
read the same scratch-vault state (see Deviations). The d dump covers the gate and hook
matrix, 18 Drive-client scenarios plus email discovery, and the dream entity, corpus and
priority layers. Those layers run over a synthetic vault and over the live vault's 111 entity
pages, read-only.

E2E on the scratch vault, engine `2971952` → `2bacfc2`: `wiki dream list-candidates --json` and
`wiki dream-entity scratch-person --dry-run` are identical, and the CLI help E2E is identical.
`wiki collect gmeet --dry-run` reaches the auth step.

CI is green (ci + secrets-scan) on all ten T07 commits.
