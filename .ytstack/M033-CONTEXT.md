---
milestone: M033
project: llm-wiki
created: 2026-10-14T18:40:00+02:00
size: L
---

# M033 -- Context (Engine modernisation + clean code)

Source pitch + audit: `.ytstack/backlog/deslop-arc.md` §3 (engine findings), §4
(principles), §6 (the arc row), §8 (not in scope). Second milestone of the operator's
de-slop arc (go 2026-10-14: "arbeite den plan komplett ab"); M032 (desktop) shipped
2026-10-14, M034 (dispatcher + surface diet) follows. Goal, exit criteria and size are cut
from the arc, re-measured on 2026-10-14 before planning — not from a Q/A session.

## Goal

The engine's Python is formatted, linted and type-checked by tools that run before every
commit and in CI, `scripts/` is an importable package instead of 36 entry scripts held
together by `sys.path` hacks, the duplicate parsers and helpers that grew next to the
0.3.0 seams are folded back onto them, and the functions no one can read in one screen are
split — with the test suite proving at every step that the engine still does exactly what
it did.

## Measured starting point (2026-10-14)

- `ruff format --check scripts hooks tests`: **289 of 379 files would change**; `[tool.ruff]`
  carries `line-length = 100` only; ruff 0.16.10 is already in the dev group.
- No type checker installed (`uv run pyright` → not found). Python 3.12.11.
- pre-commit: gitleaks + file hygiene only. CI: `secrets-scan.yml` only — the suite never
  runs on a push.
- `scripts/`: 191 `.py` files, **no `scripts/__init__.py`** (23 in sub-packages), **5
  hyphenated entry scripts**, **68 `sys.path.insert` sites**, tests via
  `pythonpath = ["scripts"]` (so `core.*` and `scripts.core.*` are two module identities —
  KNOWLEDGE C01). `cli.py` re-spawns each handler as a child process.
- **231 `noqa`** markers; under the target rule set `RUF100` reports **295 unused** (the
  audit's 183 was against ruff's defaults). Rule-set findings re-measured 2026-10-14
  (`E,F,I,UP,B,SIM,N,RUF,PL,C90`): PLC0415 991 · E501 518 · PLR2004 509 · RUF100 295 ·
  I001 228 · C901 98 · UP017 95 · F401 86 · RUF001-003 165 · RUF059 59 · PLR091x ~160 ·
  N806 32 · UP035 24 · RUF012 24 · PLW1510 23 · E402 23 · F541 22 · PLR0402 21 · E702 15 ·
  UP037 13; `.git-blame-ignore-revs` does not exist yet.
- Duplicates next to seams (audit §3.2): 17 private frontmatter entry points beside
  `core/frontmatter.py`; 5 slugify; `_setup_logging` ×4; `_load_state`/`_save_state` ×3
  beside `core/state_store.py`; `_append_daily_rollup` ×3; `_scan_inbox` ×3; 529 `print(`
  beside `core/console.py`.
- 15 functions ≥ 150 lines (list in §3.2); god modules `dream.py` 2,014 · `core/health.py`
  1,611 · `lint.py` 1,284 · `cli.py` 1,040 (+ `collectors/gmeet.py`, `migrate_config_keys.py`,
  `core/sdk_helpers.py` ≥ 1,000).
- Suite: 2,025 passed / 1 skipped in ~21 s (0.6.0).

## Exit criteria

1. **Format + lint are gates.** `ruff format --check` and `ruff check` are green over
   `scripts/ hooks/ tests/` with a modern rule set (`E,F,I,UP,B,SIM,N,RUF,PL,C90`; every
   ignore in `pyproject.toml` carries a one-line reason), in pre-commit and in CI. The
   mechanical format commit contains no logic change and its hash is in
   `.git-blame-ignore-revs`.
2. **0 unused `noqa`** (`RUF100` clean); every remaining `noqa` names its code.
3. **CI runs the engine and desktop suites** on push / PR to `main`: `uv run pytest`,
   `ruff check` + `ruff format --check`, the type checker, `npm ci && npm test && npm run
   lint` in `desktop/` — and is green.
4. **`scripts/` is the one source root** (reworded 2026-10-14 after S02-T01's probe — the
   original wording assumed a regular package): no `scripts/__init__.py` (it would reopen
   the split), no hyphenated module names, no `scripts.`-prefixed imports, `sys.path.insert`
   only in the `hooks/` bootstrap and pytest's `pythonpath`, `python -m <module>` from
   `scripts/` is how `cli.py` spawns handlers (process isolation kept), and a guard test pins
   one module identity (`core.*` vs `scripts.core.*` duplication gone, KNOWLEDGE C01 closed).
5. **Seams, not copies.** 0 private frontmatter parsers (one `core/frontmatter` grammar),
   1 slugify, 1 logging setup, state read/write only through `core/state_store`, 1
   daily-rollup appender, 1 inbox scanner — each migration preceded by a repo-wide consumer
   grep and covered by the tests the seam already has.
6. **No function ≥ 150 lines in `scripts/`** outside generated tables (AST-measured, the
   measurement committed as a test); the four god modules split where it pays, each
   ≤ 1,000 lines or a one-line reason why not in `docs/engine-layout.md`.
7. **Type checking is a gate on `core/`:** pyright `basic` (or `ty`, decided in S05 after a
   probe) green on `scripts/core/` in pre-commit and CI; the rest of `scripts/` reported,
   not gated, with the count recorded.
8. **The schema-2 `--json` contracts are typed once** (Python dataclasses → one committed
   JSON Schema) and both test suites validate their fixtures against it, so desktop and
   engine cannot drift silently.
9. **Behaviour unchanged, proven:** the suite stays ≥ 2,025 green at every task close, and
   `menu --json` / `doctor --quick --json` / `cli.py help` on a fixture vault are
   byte-identical (volatile fields normalised) before and after each refactor slice —
   snapshot test added in S01-T01. `wiki status` is bash today and joins the oracle when
   M034 moves it to Python.

## Size

L -- 5 slices, see `M033-ROADMAP.md`. Expect the split check after slicing: S03 (seams)
and S04 (long functions) are the ones that can grow past 7 tasks; if they do, the overflow
becomes M033b rather than an eighth task.

## Decisions locked in discuss phase

- 2026-10-14: Scope is `scripts/`, `hooks/`, `tests/`, `pyproject.toml`, `.pre-commit-config.yaml`,
  `.github/workflows/`. The bash layer (`wiki`, `lib/*.sh`, `install.sh`) is M034's — M033
  may add the Python `-m` entry the bash will later exec, but does not port bash commands.
- 2026-10-14: ruff is the formatter and linter (already a dev dependency; Biome stays on
  the desktop). One mechanical format commit, recorded in `.git-blame-ignore-revs`, before
  any lint fix.
- 2026-10-14: No behaviour change rides on a refactor commit. A defect found while moving
  code is fixed in its own commit with its own test (CLAUDE.md "Pfadfinderprinzip" applies,
  the fix is just not mixed into the move).
- 2026-10-14: Operator vaults are untouched. M033 adds no config knob (so no migration);
  if a refactor changes a file an operator vault pulls via `wiki update` (`hooks/`,
  `templates/`), the template-resync rule holds in the same commit.
- 2026-10-14: Engine version bumps to **0.7.0** at closeout (package layout + CI are
  operator-visible via `wiki update`: the venv's entry points change).

## Open questions

1. **Type checker: pyright or ty?** Recommendation: probe both on `scripts/core/` in S05-T01
   (install via `uv add --dev`, count findings, measure runtime); pick the one whose `basic`
   mode is green-able within the slice. Pyright is the known quantity; ty is the stack's
   vendor (Astral) and the faster one.
2. **Typed contracts: how shared?** Recommendation: Python dataclasses already own the
   payload (`core/actions.py`); emit one JSON Schema from them into `docs/contracts/`,
   validate in pytest (`jsonschema`, already transitively present — verify) and in vitest
   (`ajv` dev dependency). Alternative: generate TS types from the schema
   (`json-schema-to-typescript`) so `desktop/src/lib/actions.ts` imports instead of
   restating — decide in S05 after seeing the schema size.
3. ~~**`python -m` dispatch and the vault venv**~~ — **decided 2026-10-14 (S02-T01):**
   `scripts/` is the source root, not a package; `cli.py` runs `python -m <module>` with
   `scripts/` first on the child's PYTHONPATH and the caller's cwd inherited (S02-T03,
   `core/entry.py`); the `scripts.`-prefixed spelling is rewritten; `scripts/__init__.py`
   is not added. Full reasoning and the probe in `DECISIONS.md` 2026-10-14 ("`scripts/` is
   the engine's source root"). Renaming to `llm_wiki` stays M034's.

## Reassessment 2026-10-14T21:20:00+02:00

After **S02**, changed the roadmap (B — partial):

- The S02 slice line now says what shipped: a source root, not a package; six tasks (T06
  added mid-slice for the 72 documented by-path invocations the bootstrap removal broke).
- S03-T04 ("logging 4 → 1") widened to the inventory S02 found: 36 `logging.basicConfig`
  sites and six console-before-import modules; may split at plan-task (slice stays ≤ 7).
- S05-T05 no longer rewrites the two trees (reconciled in S02-T05); it re-verifies them.
- Recorded for M034, not scheduled here: `backlog/lazy-collector-registry.md` (registration
  on package import costs every collector verb ~0.25 s and forced the entry scripts) and
  `backlog/collect-flags-one-verb.md`.

Reason: S02's operator-path proof (T05) and the documented-invocation sweep (T06) measured
things the audit of 2026-10-14 had not: the real logging population, the import cost of the
registry pattern, and that the trees had drifted 70–85 entries from the inventory.

## Reassessment 2026-10-15T01:37:00+02:00

After **S03**, changed the roadmap:

- The S03 slice line now says what shipped (seven tasks): frontmatter 17 + 8 unnamed
  grammars → one, slugify 7 → 1, logging 33 + 4 + 8 → one entry-point setup, state 7
  writers → the store, rollup skeleton + 6 appends → one, inbox bindings inlined — every
  count re-measured by mechanism, every fold with a vault parity and a smell-based guard.
- `print` → `core/console` left the S03 line: too broad for one task and not an exit
  criterion; it belongs to M034 with the Python dispatcher (slice note of 2026-10-14).
- Recorded for later, not scheduled here: `backlog/intents-seen-state-shape.md` (the one
  list-shaped state file the store cannot hold) and `backlog/backfill-voice-rollup-shape.md`
  (the daily-rollup backfill still emits the pre-2026-06-13 voice line).
- S04 and S05 unchanged: S04-T01 re-measures the ≥ 150-line functions with `ast` (the
  audit's 15 were AST-counted, not name-counted); S05-T05 inherits two toolchain lessons
  already in KNOWLEDGE (ruff ≥ 0.16 formats Markdown fences — `*.md` now excluded; a
  formatter with an empty path variable is a whole-project run).

Reason: S03's recurring finding — the audit's def-name counts undercounted every seam
(3 → 7 slug copies, 3 → 7 state writers, 3 → 6 hand-typed rollup appends, 17 → 25
frontmatter grammars) — changes how S04 should count too: by the mechanism, verified on
the live tree, with the guard asserting the predicate the fold established.
