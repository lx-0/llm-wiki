---
milestone: M005
slice: S03
task: T03
project: llm-wiki
closed: 2026-05-15T19:05:00Z
verification: passed
---

# M005-S03-T03 -- Summary

## Outcome

Audit of `scripts/compile.py` confirms zero code change needed. The infrastructure for commitment-extraction routing was already in place when the slice plan was written:

- `compile.py:230` — `allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"]` (Write + Edit enable both new-stub creation and existing-page mutation).
- `compile.py:231` — `permission_mode="acceptEdits"` (no prompts block routing).
- `compile.py:228` — `cwd=str(ROOT_DIR)` (relative paths in the new prompt rules resolve correctly).
- `compile.py:233` — `system_prompt=render("compile_main_system")` carries no path restrictions (verified by inspecting `prompts/compile_main_system.md`).
- `compile.py:324` — directory-bootstrap loop ensures both `knowledge/people/` and `knowledge/projects/` exist before any compile pass starts; the LLM never hits a missing-parent error when stubbing a new person.

The routing semantics live entirely in the prompt rules from T01 (commitment extraction) and T02 (entity resolution). `compile.py` faithfully carries them out.

## Deviations from plan

The slice plan implied T03 was a code-change task. The audit shows the configuration was already correct. T03 ships as a documented audit. If a future real-substrate canary (T05) reveals a routing gap, that becomes a fresh ticket — not anticipated for M005-S03.

## Follow-ups

- T04 fixture test exercises T01 + T02 prompt rules on a synthetic jamie transcript.
- T05 real-substrate canary stress-tests the end-to-end pipeline on a real Drive Doc.

## Verification

```
grep -n "allowed_tools" scripts/compile.py
# → 230:                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],

grep -nE 'people|projects' scripts/compile.py | grep -i 'subdir'
# → 324:    for subdir in ["concepts", "connections", "qa", "people", "projects"]:

uv run --project . pytest -q tests/
# → 230 passed in 0.49s (unchanged — no code change, no test added)
```

Result: **passed**.
