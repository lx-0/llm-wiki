---
milestone: M026
project: llm-wiki
created: 2026-05-23T14:09:59+0200
size: M
---

# M026 -- Context

## Goal

Split `compile_file`'s 404-LOC dispatcher into a pure `decide_route` + typed `CompileOutcome`, so compile routing and the substrate→model/max_turns precedence ladder become table-testable — a structural refactor with **no behavior change**.

## Exit criteria

- `decide_route(source, content) → Route` is a pure function (source path + content + CONFIG only) returning `Skip` / `IndexOnly` / `HealthStub` / `Compile`, covered by a route-selection + dispatch-precedence table test (no SDK / state / filesystem mocking).
- `compile_file` is a thin `match route:` dispatcher returning a typed `CompileOutcome`; the legacy magic-key return dict (`{"_skipped": …}` / `{"_failure": …}` / usage-dict) is gone.
- `_STATE_MUTATING_SKIPS` and its reload-after-skip branch are deleted; `main()` has a single state-save site persisting the ingested-hash via `outcome.ingest_hash`.
- Dead `compile.py:_build_owner_block` removed.
- Full pytest suite green; an E2E smoke `wiki compile` on the lxw vault still produces articles + per-file skips/state as before (modulo LLM non-determinism).

## Source design

Full design + slice breakdown grilled via `improve-codebase-architecture` 2026-05-23: **`.ytstack/backlog/compile-dispatch-seam.md`** (committed `1510986`). Supersedes the residual of architecture-deepening **#5**. CONTEXT.md (repo root) carries the Compile-route / `decide_route` / `CompileOutcome` vocab.

## Decisions locked in discuss phase

- 2026-05-23: **D1 — coarse route taxonomy** (`Skip` / `IndexOnly` / `HealthStub` / `Compile`), NOT distinct Single/Chunked variants. The single-vs-chunked split is `classify()`'s output (already its own tested module); a chunked variant would duplicate that test surface. `decide_route` runs `classify()` so the `Compile` variant carries the `Classification`.
- 2026-05-23: **D2 — single state-save + typed `CompileOutcome`.** Execution handlers never touch state; `main()` is the single persist site (persist iff `outcome.ingest_hash`). Deletes `_STATE_MUTATING_SKIPS` + the magic-key dict. Rejected: keep self-persist (preserves the leak the seam exists to remove).
- 2026-05-23: **Memory pre-pass stays on the execution side.** `resolve_project_slug` + `ensure_timeline_section` writes a `## Timeline` section (I/O), so it lives inside the `Compile` handler (`run_compile`), NOT in pure `decide_route`.
- 2026-05-23: **`commit_article` stays cancelled.** The agent writes `knowledge/**` itself via path-scoped tool-use; `result.article` is only a success signal. There is no pure-I/O commit stage to extract.
- 2026-05-23: **No config knobs added/removed** → the project's config-migration hard-rule does not apply (import/structure only).

## Open questions

(Resolve during slicing — none blocking. The dispatch-table relocation, `SUBSTRATE_PROMPTS` / `_DEFAULT_DISPATCH` byte-for-byte preservation, is a known sub-agent-porting risk; structural-diff after the move.)
