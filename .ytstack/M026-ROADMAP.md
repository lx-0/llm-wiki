---
milestone: M026
project: llm-wiki
size: M
created: 2026-05-23T14:09:59+0200
status: planned
total_slices: 4
completed_slices: 3
---

# M026 Roadmap

**Goal:** Split `compile_file`'s 404-LOC dispatcher into a pure `decide_route` + typed `CompileOutcome` — routing/dispatch becomes table-testable, no behavior change.

**Exit criteria:**
- Pure `decide_route(source, content) → Route` (Skip/IndexOnly/HealthStub/Compile), table-tested for route selection + dispatch precedence.
- `compile_file` = thin `match route:` returning `CompileOutcome`; magic-key dict gone.
- `_STATE_MUTATING_SKIPS` + reload-after-skip deleted; `main()` single state-save via `ingest_hash`; dead `_build_owner_block` removed.
- Full pytest green + lxw E2E smoke unchanged (modulo LLM non-determinism).

## Slices

Slice detail lives in per-slice `M026-S##-PLAN.md` files. Full pre-grilled breakdown in `.ytstack/backlog/compile-dispatch-seam.md` — these are written directly from the design (the `slice-milestone` gate aborts on named slices; documented workaround).

Pure refactor — each slice ends green + the engine still compiles a fixture identically (modulo LLM non-determinism).

- [x] S01 -- Types: `CompileOutcome` + `Route` union in `compile_stages/types.py` + `route.py` scaffold (1-2 tasks) — shipped `4647d47`
- [x] S02 -- `decide_route` extraction (shipped 2c4335c+aad8541): relocate `SUBSTRATE_PROMPTS`/`_DEFAULT_DISPATCH`/`_substrate_key`/`_frontmatter_*` + role/skip/dispatch/classify into pure `route.py:decide_route`; table-test route + precedence. `compile_file` calls it but still executes inline (behavior identical). (2-3 tasks)
- [x] S03 -- Execution handlers (shipped e6c04df): extract `index_source_and_final` / `record_health_stub` / `run_compile` (incl. memory pre-pass + chunk-loop) into `execute.py`; `compile_file` becomes the `match` dispatcher returning `CompileOutcome`. (2-3 tasks)
- [ ] S04 -- `main()` rewire: loop consumes `CompileOutcome`, single `save_state` via `ingest_hash`; delete `_STATE_MUTATING_SKIPS` + magic-key dict + dead `_build_owner_block`; lxw E2E smoke. (2 tasks)

## Run order

Slices execute sequentially (S01 types → S02 decision → S03 execution → S04 wire-up + cleanup). Each is a self-contained green step. After each slice, `ytstack:reassess-roadmap` checks the plan still fits.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
