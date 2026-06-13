---
milestone: M028
slice: S01
task: T01
project: llm-wiki
closed: 2026-06-13T16:27:12+0200
verification: passed
---

# M028-S01-T01 -- Summary

## Commits

- `db60226` -- feat(correct): sandbox `apply()` agent — drop Bash + path-scope hook (M028-S01-T01, issue #5)

(Ref is in the subject parens, not the `M028-S01-T01:` prefix form — `git log
--grep "^M028-S01-T01"` won't match; the loose grep does.)

## Outcome

`wiki correct apply`'s agent now runs sandboxed. The inline `ClaudeAgentOptions`
in `apply()` was extracted into a module-level `_apply_agent_options(capture)`
helper and hardened to mirror the safe `reconcile_fact()` pattern:
`allowed_tools=["Read","Glob","Grep","Write","Edit"]` (Bash removed — the agent
can no longer `rm`/`git mv`), a PreToolUse `Write|Edit` path-scope hook over
`[KNOWLEDGE_DIR, DAILY_DIR, INDEX_FILE, LOG_FILE]`, `permission_mode="default"`
(was `acceptEdits`), and `max_turns=CONFIG.limits.correct_apply_max_turns` (new
knob, default 50 = the old hardcoded value, migration in the same commit). New
`tests/test_correct_apply.py::test_apply_options_sandboxed` pins the options.

## Deviations from plan

- **Verification path wrong in the plan.** The plan said `cd .wiki && uv run
  pytest …`. `.wiki/` is the *vault-side* install path; the engine dev repo runs
  tests from the repo root (`uv run pytest`, venv at `./.venv`, `pythonpath =
  ["scripts"]`). Ran from root.
- **3 migration fixture-count tests needed updates** (anticipated as a touched
  file, but the specifics): `test_migrate_config_file_round_trip` count
  91→92 + the "26 limits additions" enumeration → 27; two "fully-current"
  fixtures (`no_change_when_fully_current`, `idempotent`) gained
  `correct_apply_max_turns: 50`.
- **`reconcile_fact()` NOT refactored** to share the new helper — intentional. It
  has a deliberately tighter scope (`CONCEPTS_DIR` only) and its own turn knob;
  sharing would over-couple two different agents. Avoided premature abstraction.

## Follow-ups

- **S01-T02 (already planned):** `make_path_scope_hook` is allow-list-only, so
  `knowledge/facts/` is still writable in this state. T02 adds a `denied_subpaths`
  param to close it. No "facts/-protected" claim until then.
- **S01-T06 (already planned):** the hook's runtime deny behaviour is proven
  elsewhere (compile/dream/reconcile, live since 2026-05-18), but the end-to-end
  "agent annotates, deletes nothing" assertion is the golden repro test in T06.
- KNOWLEDGE.md updated: engine-repo test command is `uv run pytest` from root,
  not `cd .wiki` (vault-side) — so future task-plan verification commands are right.

## Verification

Command: `uv run pytest` (from repo root) -- passed. `test_correct_apply.py` +
`test_migrate_config_keys.py` green; full suite **1320 passed, 1 skipped**.
