---
milestone: M034
slice: S04
task: T03
project: llm-wiki
closed: 2026-10-16T02:06:37+02:00
verification: passed
---

# M034-S04-T03 -- Summary

## Commits

- `97918ac` -- M034-S04-T03: the seed's special merges in Python — the plugin-list union, the two button registries by id, the .env stanza append — held to 22 goldens recorded from the bash and to copies of lxw's configs

The task was planned in `c04fd4f`, T02's summary commit.

## Outcome

The seed's special merges are pure Python in `core/seed.py`:
- **`union_list`:** community-plugins.json and appearance.json's snippets. It returns the
  engine entries the file lacks; only then does it return a merged file, the jq `unique`
  of both lists.
- **`engine_entries` + `merge_registry`:** by id, in place. The engine's fields go over an
  entry, and other fields stay. The legacy object form is read the way the plugin migrates
  it. It returns the ids added and updated.
- **`env_missing` + `env_appended`:** the template's active names, sorted. A commented
  `# KEY=` counts as present. Stanzas follow the awk rule and are appended as `\n\n%s\n`.
- **`ShapeError`** marks every shape jq errs on.

`core/jqjson.py` adds `unique` (jq's order across types) and `subtract`.
`agent_buttons.registry_entries(key)` hands the agent entries to the command, so `core`
stays below `dashboard`.

22 goldens from the bash merges hold Python to the report and to the file as written:
10 list, 8 registry, 4 env. Copies of lxw's five configs give the same files and reports.

## Deviations from plan

- **The dashboard rewrite needed no port:** it is Python already
  (`agent_buttons.update_dashboard` / `has_region`), and T04 calls it in-process.
- **The agent entries are passed in, not fetched by `core`.** `engine_entries` takes them
  from `agent_buttons.registry_entries`, which the plan did not name.
- **The env key order is code-point order.** The bash used the caller's locale for
  `sort -u`, which gives the same order for the template's upper-case names.
- **A test-driver bug was caught in the goldens.** The `_agent_entries` stub read its own
  `$5`, so the first recording showed every registry as "trouble". The record was read
  before commit, fixed and re-recorded.

## Follow-ups

- **T04 builds the command on these functions:**
  - the messages per kind (the oracle goldens hold them);
  - missing-file seeding (copy, or template + engine for the registries);
  - check, force and targeted paths;
  - `--extract-custom`;
  - the help;
  - the dashboards refresh in-process.
- The live-copy parity scripts (`/tmp/live-parity.py`, `/tmp/live-parity-merges.py`) are the
  shape for T04's end-to-end check on a copy of lxw.

## Verification

Command: `uv run --frozen pytest tests/test_seed_merges.py tests/test_seed_core.py -q` --
passed (47 + 60).

Gates: ruff, format and ty are clean. Live parity on copies of lxw: 0 failures. CI is
green on `97918ac`. Full suite at `97918ac`: 2653 passed, 1 skipped.
