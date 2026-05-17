---
milestone: M018
slice: S03
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M018-S03 — Slice Plan

**Goal:** Pure LLM-call function `compile_source(content, metadata) → CompileResult` lives in `scripts/compile_stages/compile.py` and owns prompt-assembly + owner-block + pre-flight 60kb gate + kind-unknown retry-ladder + SDK call + failure classification. No file I/O, no state writes, no `knowledge/` writes.

## Tasks

- [ ] T01 -- Define `CompileResult` dataclass in `scripts/compile_stages/types.py`: `status: Literal["ok", "skipped", "failed"]`, `article: str | None` (markdown body), `frontmatter_extra: dict`, `cost_usd: float`, `skip_reason: str | None`, `failure_kind: str | None`. Plus `CompileMetadata` for the input side (source_path, compile_role, model_id, max_turns, substrate_type).
- [ ] T02 -- Create `scripts/compile_stages/compile.py:compile_source(content, metadata) → CompileResult`. Move the SDK call body from `compile.py` (lines ~789-960) into the new function. Owner-block helper, render(), preflight (`assert_prompt_within_budget`), retry ladder, classify_failure, can_use_tool gate construction — all called from within this function.
- [ ] T03 -- Move the kind-unknown skip-and-flag branches (M010, `compile.py:1049-1078`) into the new function. Skip statuses become `CompileResult(status="skipped", skip_reason=...)`. Cost accumulation moves with them.
- [ ] T04 -- Add `tests/test_compile_source.py` with ≥4 cases mocking SDK ResultMessage: (a) success returns CompileResult.status=ok + body + cost, (b) `kind=unknown` on long-context model returns status=skipped, (c) `kind=max_turns` returns status=skipped, (d) pre-flight 60kb fail returns status=failed before SDK call. Use existing `tests/conftest.py` SDK mocks.
- [ ] T05 -- Wire `compile.py:main()` per-file loop to call `compile_source()`. The loop reads result + branches on status — does NOT inline the SDK call. Run S01 regression vault — must stay green. State-save logic stays in `main()` until S04 lifts it.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `compile_source()` is independently importable, ≥4 unit tests covering happy path + 2 skip paths + 1 fail path, regression vault byte-identical.

## Notes

This is the load-bearing slice — `compile_source()` carries the most logic. Resist re-architecting the retry ladder during extraction (mechanical move only). Owner-block injection (M009) and pre-flight (M010) come along verbatim. The `can_use_tool` gate construction (M017-day-1 hardening) stays — `compile_source` builds the agent_options including the gate.
