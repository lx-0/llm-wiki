# Compile-dispatch seam — `compile_file` → pure `decide_route` + typed `CompileOutcome`

**Status:** Designed 2026-05-23 via `improve-codebase-architecture` (grilling loop). Ready for `ytstack:plan-milestone` pickup. Supersedes the residual of architecture-deepening **#5** (`compile.py` orchestration), whose original framing is now obsolete — see "Corrected diagnosis" below.

**Vocabulary:** domain/arch terms from `CONTEXT.md` (Compile route / decide_route / Route / CompileOutcome added 2026-05-23 in the same grilling arc). Architecture terms from improve-codebase-architecture's LANGUAGE.md.

---

## Corrected diagnosis (why #5's old framing is dead)

The backlog #5 ("select → extract → commit, commit still inline, HIGH, got WORSE") was written before M018 landed. After M018 the picture is different:

- **`select_files()`** — extracted, pure-ish (`compile.py:103`). ✓
- **`compile_source()`** — the LLM-call stage, cleanly extracted to `compile_stages/compile.py`. ✓
- **`run_post_passes()`** — Producer orchestrator, extracted to `compile_stages/post_passes.py`. ✓
- **commit** — *correctly does not exist*. The agent writes `knowledge/**` itself via path-scoped Write/Edit tool-use during the SDK call; `result.article` (compile.py:800, 1037) is only a non-empty success signal, never written to disk. The M018-S03 `commit_article` cancellation was right (see `commit-article-manifest.md`), not a gap. The Explore agent's "commit still in the loop" finding was a misread.

So the deletion-test that made #5 a HIGH was already paid down by M018. **The residual is exactly one thing:** `compile_file()` (404 LOC, `compile.py:406-810`) is a monolithic per-file *dispatcher* that interleaves three concerns:

| Concern | Where (compile.py) | Testable today? |
|---|---|---|
| **A. Route decision** — final-only / source-and-final / skip-list / health-stub / aggregated-memory / default | scattered through all 404 lines | No |
| **B. Deterministic execution** — source-and-final index-write (459-500), health-rollup stub record (535-543) — full mini-pipelines inline, each self-persisting state | inline | No (side-effects only) |
| **C. LLM dispatch params** — substrate→prompt/model/max_turns 4-level precedence | 545-643 (~80 LOC, most-commented/most-bug-prone block in the engine) | No |

**Shallowness:** you cannot answer *"what route does file X take, with what model/turns?"* without executing `compile_file` — which means mocking SDK + state + filesystem. `tests/test_compile_role_dispatch.py:9` literally documents this: *"Full compile_file roundtrip with mocked SDK + state/index files is deferred."* The interface is as complex as the implementation = shallow.

**Honest re-rating:** this is a **MEDIUM** ("make routing a testable decision"), not the HIGH the backlog advertises. The HIGH was earned and spent by M018.

---

## Decisions (grilled 2026-05-23)

### D1 — Route taxonomy: COARSE (4 variants), classify INSIDE the decision

`Skip / IndexOnly / HealthStub / Compile`. The single-vs-chunked split is NOT a separate route variant — it is just `classify()`'s output, and `classify` (`compile_stages/classify.py`) is already its own tested module. A `ChunkedCompileRoute` variant would re-test what classify already covers and the chunk-loop circuit-breaker is execution orchestration, not routing. **Refinement:** `decide_route` runs `classify()` so the `Compile` variant carries the `Classification` — keeping `decide_route`'s output a complete, assertable description of "what will happen."

Rejected: distinct Single/Chunked variants (duplicate test surface, no new leverage).

### D2 — State-save + return contract: SINGLE persist point + typed `CompileOutcome`

Execution handlers never touch state. `compile_file` returns one typed `CompileOutcome` (status + optional `ingest_hash` + cost/tokens), replacing the legacy magic-key dict (`{"_skipped": …}` / `{"_failure": …}` / usage-dict). `main()` becomes the **single state-save site**, persisting `state["ingested"][rel]=hash` iff `outcome.ingest_hash`.

This deletes the `_STATE_MUTATING_SKIPS` registry (`compile.py:846`) and its leaky reload-after-skip dance (`compile.py:958-964`) — today a deterministic handler self-persists and `main()` must *remember* to reload state so the loop's own `save_state` doesn't clobber the mark. That split-persist contract is the exact leak the seam exists to remove.

Iron-rule "no gap between capture and persist" is preserved: the expensive LLM success path *already* persists in `main()` (compile.py:1049), so deterministic routes doing the same adds no meaningful gap, and they're cheap to redo anyway.

Rejected: keep self-persist + dict return (smaller diff, but preserves the leak — contradicts the "pure dispatch" goal the operator chose).

---

## Target shape

New module `scripts/compile_stages/route.py`:

```python
# Pure decision — depends only on source path + content + CONFIG.
def decide_route(source: Path, content: str, *, force: bool = False) -> Route: ...

Route = Skip(reason) | IndexOnly(title, wikilinks) | HealthStub() | Compile(metadata, classification)
```

`decide_route` absorbs the pure pre-LLM logic currently inline in `compile_file`:
- empty-body / dry-run guards (dry-run stays in main() — it's an arg, not a property of the source)
- `infer_compile_role` + final-only skip + source-and-final detection
- substrate-type skip-list check
- health-rollup stub detection (`_health_rollup_body_is_stub`)
- the **dispatch precedence ladder** (concern C): `SUBSTRATE_PROMPTS` / `_DEFAULT_DISPATCH` → (prompt, model, max_turns), incl. substrate-model-wins / force-long-context / size-escalation precedence
- `classify(content, source)` → carried in the `Compile` variant

**Relocate** `SUBSTRATE_PROMPTS`, `_DEFAULT_DISPATCH`, `_substrate_key()`, `_frontmatter_*` helpers out of `compile.py` into `route.py` (or a `compile_stages/dispatch.py`). They are module-local to compile.py today (no external importers) — clean move.

Execution handlers (new `scripts/compile_stages/execute.py`, or fold into existing modules):
- `index_source_and_final(source, content, route) -> CompileOutcome` — wikilink extract + `knowledge/index.md` append; returns `ingest_hash=True`. No state write.
- `record_health_stub(source) -> CompileOutcome` — returns `ingest_hash=True`. No state write.
- `run_compile(source, content, route) -> CompileOutcome` — runs the **memory pre-pass** (I/O: `resolve_project_slug` + `ensure_timeline_section`), enriches `CompileMetadata`, then branches single vs aggregated-memory (the existing chunk-loop + circuit-breaker, lines 711-777) and calls `compile_source`. Maps `CompileResult` → `CompileOutcome`.

`CompileOutcome` lives in `compile_stages/types.py` (next to `CompileResult` / `CompileMetadata`).

`compile.py:compile_file` collapses to thin dispatch:

```python
async def compile_file(source, dry_run=False, *, force=False) -> CompileOutcome:
    if dry_run: return CompileOutcome(status="skipped", skip_reason="dry_run")
    content = source.read_text(encoding="utf-8")
    route = decide_route(source, content, force=force)
    match route:
        case Skip(reason):       return CompileOutcome(status="skipped", skip_reason=reason)
        case IndexOnly():        return index_source_and_final(source, content, route)
        case HealthStub():       return record_health_stub(source)
        case Compile():          return await run_compile(source, content, route)
```

`main()` loop consumes `CompileOutcome` uniformly: `match outcome.status` (compiled/skipped/failed) → one `save_state` site, persist iff `outcome.ingest_hash`. The failure-streak / abort logic (compile.py:965-1016) reads `outcome.failure` instead of `result["_failure"]`.

---

## Purity boundary (what stays impure, on purpose)

`decide_route` is pure: source path + content + CONFIG → Route. Testable by setting CONFIG knobs and asserting the Route. The **memory pre-pass writes a `## Timeline` section** — I/O with side-effects — so it stays in `run_compile` (execution), NOT in the decision. This is correct, not a compromise: the decision says "this is a Compile route"; the handler does the I/O the route implies.

---

## What deletes / cleanup riding along

- `_STATE_MUTATING_SKIPS` frozenset + the reload-after-skip branch (compile.py:846, 958-964).
- The magic-key return dict (`_skipped` / `_failure` / usage-dict) across compile_file + main().
- **Dead code:** `compile.py:371 _build_owner_block()` — defined, never called (the live copy is `compile_stages/compile.py:76`). Verified: only self-reference in compile.py. Delete.

---

## Tests

**Survive / refactor:** `test_compile_role_dispatch.py` (pure frontmatter helpers move with the helpers), `test_compile_source.py`, `test_compile_stages_types.py`, `test_compile_reliability.py`, `test_compile_role.py`.

**New (the leverage):**
- `test_decide_route.py` — TABLE test the route decision: empty→Skip, final-only→Skip, source-and-final→IndexOnly, skip-list type→Skip, health stub→HealthStub, normal→Compile. No SDK/state/fs mocking.
- Dispatch-precedence table (concern C, the money-bugs): substrate_model wins over size-escalation; force-long-context tier; 50KB+ size-escalation only on compile_main route; Haiku-routed lean prompts not escalated. These caused real $5-10/file blowouts (compile.py:601-603 scar tissue) and are untestable today.
- `decide_route` carries the right Classification (single vs aggregated-memory) for a memory substrate.
- Handler tests: `index_source_and_final` returns `ingest_hash=True` + appends index entry; `record_health_stub` returns `ingest_hash=True`.

**Non-goal:** byte-identical regression of compiled articles — LLM output is non-deterministic (see `feedback_llm_output_non_deterministic`). Test deterministic inputs (routes, dispatch params, outcomes), not LLM bodies. E2E smoke on a real lxw fixture at slice close (M018 proved unit-with-SDK-mocked misses real bugs — `feedback_e2e_smoke_irreplaceable`).

---

## Proposed slice breakdown (for plan-milestone)

Pure refactor — **no behavior change intended**. Each slice ends green + the engine still compiles a fixture identically (modulo LLM non-determinism).

- **S01 — Types.** Add `CompileOutcome` + the `Route` union to `compile_stages/types.py` (+ `route.py` scaffold). Unit tests for the types. No wiring. (1-2 tasks)
- **S02 — `decide_route` extraction.** Move `SUBSTRATE_PROMPTS` / `_DEFAULT_DISPATCH` / `_substrate_key` / `_frontmatter_*` + role/skip/dispatch/classify logic into `route.py:decide_route`. `compile_file` calls it but still executes inline (behavior identical). Table-tests for route + dispatch precedence. (2-3 tasks)
- **S03 — Execution handlers + `CompileOutcome` return.** Extract `index_source_and_final` / `record_health_stub` / `run_compile` (incl. memory pre-pass + chunk-loop) into `execute.py`; `compile_file` becomes the `match` dispatcher returning `CompileOutcome`. Handler tests. (2-3 tasks)
- **S04 — main() rewire + cleanup.** Loop consumes `CompileOutcome`, single `save_state` via `ingest_hash`. Delete `_STATE_MUTATING_SKIPS`, magic-key dict, dead `_build_owner_block`. E2E smoke on lxw. (2 tasks)

Size: **M** (4 slices, ~8-10 tasks). No config-key changes → no `migrate_config_keys.py` entry needed (the project's config-migration hard-rule does not apply; this is import/structure only).

---

## Risks / non-goals

- **No config knobs added/removed** → config-migration rule N/A.
- **commit_article stays cancelled** — agent-side writes are the architecture, not debt.
- **Watch the dispatch relocation** — `SUBSTRATE_PROMPTS` carries substrate-specific tuning (model + max_turns per type); moving it must preserve every entry byte-for-byte. Sub-agent porting risk (`feedback_subagent_for_focused_extraction`): structural diff against the original after the move.
- **Memory pre-pass I/O ordering** — `ensure_timeline_section` must still run before the SDK call inside `run_compile`; don't let the decision/execution split reorder it.
