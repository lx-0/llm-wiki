---
milestone: M027
slice: S01
task: T01
project: llm-wiki
closed: 2026-06-07T12:55:00+0200
verification: passed
---

# M027-S01-T01 -- Summary

## Commits

- `add19eb` -- feat(config): personal.watched_folders schema (M027-S01-T01)

(The ytstack `M###-S##-T##:`-prefix grep finds nothing -- the commit uses the
conventional-commit subject `feat(config): … (M027-S01-T01)` with the ref in
parens, not as a prefix. Hash recorded directly.)

## Outcome

`personal.watched_folders` is now a real config key: `Personal.watched_folders:
list[dict]`, each entry `{id, kind: local|smb, path|share, include?, exclude?}`,
default `[]`. `_validate_watched_folders_schema()` (in `scripts/core/config.py`)
rejects entries with a missing/empty `id`, a `kind` outside `{local, smb}`, a
`local` entry without `path`, or an `smb` entry without `share` -- raising
`ConfigError` that names every offending entry. It is wired into `config.load()`
right after `_validate_accounts_schema`, so a bad config fails fast at load.
`migrate_config_keys.py` injects `personal.watched_folders: []` into existing
operator vaults on `wiki update` (KEY_ADDITIONS, same-commit migration per the
config-knob rule). `config.example.yaml` documents the shape with a local + smb
example. Validation only -- nothing reads or scans the filesystem yet (that is
S02).

## Deviations from plan

- Tests landed in a **dedicated `tests/test_watched_folders_config.py`** (9
  tests) rather than only extending `test_migrate_config_keys.py` as the plan
  said -- cleaner per-feature home and the natural place S02+ behavior tests
  will grow. `test_migrate_config_keys.py` was still touched: the hard change
  count `83 → 84` plus the two idempotence fixtures gained `watched_folders: []`
  (expected characterization-test updates for a new KEY_ADDITIONS key).
- Added **two `load()`-wiring tests** beyond the plan's verification, and proved
  they actually test the wiring by temporarily removing the `load()` call and
  watching `test_load_rejects_bad_watched_folders` fail ("DID NOT RAISE") before
  restoring it -- guards the "mocks mask wiring bugs" failure mode.
- config.py field placed next to `curiosity_folders` (curiosity-substrate
  cluster) rather than next to `inbox_bridges`; same dataclass, no behavioral
  difference.

## Follow-ups

- **S01-T02** (answer-landing contract) is the next task -- the one remaining
  upfront design decision S03/S04 depend on.
- `include`/`exclude` globs are accepted but their glob *syntax* is not
  validated yet; defer glob-validation to S02 (where the walker consumes them).
- Cosmetic: test runs emit a `VIRTUAL_ENV ... does not match` warning -- a stale
  `VIRTUAL_ENV` env var pointing at a different llm-wiki checkout
  (`yesterday-ai/llm-wiki/.venv`); `uv --project .wiki` ignores it. Not this
  task's concern; noted once.

## Verification

Commands:
- `uv run --project .wiki python -m pytest -q` -- **passed** (1207 green, 0 fail).
- `_validate_watched_folders_schema({'watched_folders':[{'id':'x','kind':'bogus'}]})`
  -- **raised** `ConfigError` naming entry `x` and the bad `kind`, as required.

verification: passed.
