---
milestone: M007
slice: S01
task: T01
project: llm-wiki
status: done
completed: 2026-05-16T15:40:00Z
---

# M007-S01-T01 -- Summary

## Outcome

Created `scripts/core/compile_role.py` (89 LOC) with:
- `CompileRole = Literal["source-only", "source-and-final", "final-only"]`
- `VALID_ROLES: frozenset[str]` (T03 lint consumes this)
- `LOCATION_DEFAULTS: dict[str, CompileRole]` for the 4 known top-level segments (`raw`, `daily`, `inbox`, `knowledge` → all default `source-only`; operator marks `final-only` explicitly in frontmatter to archive)
- `infer_compile_role(path, frontmatter, *, default_by_location=True, vault_root=None)` pure function with explicit-override-wins
- `_location_class(path, vault_root)` private helper

Pure module — no global config dependency. T02 callers will plumb `CONFIG.compile_role_default_by_location` into the keyword arg.

## Deviations from plan

- Plan said `scripts/core/frontmatter.py (or schema location)`. No central frontmatter module exists (parsing is scattered: `compile.py::_frontmatter_type`, `utils.py::_parse_fact_frontmatter`, `agent_spec.py`). Created dedicated `scripts/core/compile_role.py` instead — single-responsibility, minimal blast radius, no refactor.
- File length 89 LOC vs ~60 estimated (docstring + absolute-path/vault_root try/except). Still trivially within one-context-window.

## Follow-ups

- **T02**: config knob `compile_role_default_by_location: bool = true` in `core/config.py` + `config.example.yaml` + `migrations/migrate_config_keys.py` (same-commit hard-rule).
- **T03**: `scripts/lint.py` imports `VALID_ROLES` for enum validation; uses `infer_compile_role()` + git-history for cross-location-move warning.
- **T04**: pytest formalization including edge cases (path-outside-known-segments, vault_root mismatch).

## Verification

7-assertion smoke test passed (`OK` printed, exit 0):
1. Explicit override wins → `final-only`
2. `raw/notes/x.md` empty frontmatter → `source-only`
3. `knowledge/concepts/x.md` empty frontmatter → `source-only`
4. Invalid `'bogus'` → `ValueError`
5. `default_by_location=False` → `source-only` short-circuit
6. Explicit `source-and-final` returns `source-and-final` (long-form slot)
7. Absolute path + `vault_root=` resolves relative correctly

```bash
uv run python -c "from scripts.core.compile_role import infer_compile_role, VALID_ROLES; ... print('OK')"
# exit 0 + OK printed
```

## Commits

- `ab37108` — docs(ytstack): plan M007-S01-T01 + author-attribution backlog
- `76e24e4` — feat(compile-role): scripts/core/compile_role.py — M007-S01-T01

## Commits so far

- `1b6507a` -- docs(ytstack): M007-S01-T01 done — checkbox flip + summary (2026-05-16T15:38:06Z)
