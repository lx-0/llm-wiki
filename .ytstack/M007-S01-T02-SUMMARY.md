---
milestone: M007
slice: S01
task: T02
project: llm-wiki
status: done
completed: 2026-05-16T15:50:00Z
---

# M007-S01-T02 -- Summary

## Outcome

Added `compile_role_default_by_location: bool = True` knob across 3 files (same-commit per project hard-rule):

1. **`scripts/core/config.py`** — new field in `Limits` dataclass (line ~307), default `True`, sibling to `compile_skip_on_long_context_unknown`. Docstring explains the toggle: when on, `infer_compile_role()` uses LOCATION_DEFAULTS; when off, all files without explicit `compile_role:` short-circuit to `source-only`.
2. **`config.example.yaml`** — operator-facing comment + `compile_role_default_by_location: true` under `limits:` (line ~232).
3. **`scripts/migrations/migrate_config_keys.py`** — extended `KEY_ADDITIONS["limits"]` so existing operator vaults get the key injected on `wiki update`.

## Deviations from plan

None. Each file matched the planned insertion point exactly.

## Follow-ups

- **T03**: `scripts/lint.py` enum validation + cross-location-move warning. Imports `VALID_ROLES` from `scripts.core.compile_role`. Reads `CONFIG.limits.compile_role_default_by_location` to know whether default-inference is in play.
- **T04**: pytest formalization. Includes a smoke test that `CONFIG.limits.compile_role_default_by_location` exists with default `True` (regression check).
- **S02-T01 (downstream)**: actual callers of `infer_compile_role()` plumb `default_by_location=CONFIG.limits.compile_role_default_by_location`.

## Verification

3-part smoke (all green, exit 0):
1. `CONFIG.limits.compile_role_default_by_location is True` (dataclass default applies)
2. `KEY_ADDITIONS["limits"]["compile_role_default_by_location"] == True` (migration would inject correctly)
3. `grep -q 'compile_role_default_by_location: true' config.example.yaml` (operator-facing example present)

## Commits

- `f3e8fa7` — feat(config): compile_role_default_by_location knob — M007-S01-T02
