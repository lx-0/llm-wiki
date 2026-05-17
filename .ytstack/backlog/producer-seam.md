# Producer seam + compile.py orchestration — design doc

Grilled out of `/improve-codebase-architecture` walk refresh (2026-05-17). Two milestones, sequenced. Vocabulary from `CONTEXT.md` (Producer, ProducerSpec, ProducerResult, ProducerRegistry — added in the same arc) and improve-codebase-architecture's LANGUAGE.md (module / interface / depth / seam / adapter / leverage / locality / deletion-test).

Consumed by `ytstack:plan-milestone` when these are next prioritized.

---

## Why two milestones, not one

A bundled cut (Producer Protocol + compile.py stage split + post-pass extraction, all in one milestone) makes the regression surface cover two refactors at once. Splitting:

- **Milestone-A — Producer seam in place.** compile.py's per-file loop structure is preserved; three hardcoded `await maybe_X(source)` calls become `for p in ProducerRegistry.all(): await orchestrate(p, source)`. The three concrete producers conform to the new Protocol. Regression check: byte-identical output of `wiki compile` on a fixture vault.
- **Milestone-B — compile.py orchestration refactor.** Three pure stages (`select_sources` / `compile_source` / `commit_article`) emerge; post-passes lift out of the per-file loop into a `run_post_passes()` orchestrator that consumes ProducerRegistry. The Producer seam is the natural seam between the per-file loop and the post-pass policy.

Milestone-A locks the interface; Milestone-B uses it. Doing #2 first would mean cutting stages without the Producer interface settled, then re-cutting.

---

## Milestone-A — Producer seam

### Locked decisions

1. **Failure contract = α.** Orchestrator wraps every `Producer.run()` in try/except. A `failed` Producer logs + tallies but **never blocks** the source's compile-state save. Fixes a quiet bug: today, if `maybe_generate_curiosity_requests()` raises, the state-save at `compile.py:1288` is skipped, so the next compile run re-spends Claude SDK tokens recompiling the same source.

2. **Two gates, both declarative on Spec, both evaluated by the orchestrator** (not by the Producer):
   - `enabled_config_key: str | None` — None = always on; str = e.g. `"features.extract_takes"`.
   - `source_glob_config_key: str | None` — None = applies to every source; str = e.g. `"limits.extract_takes_source_globs"`.
   Producers do not check their own gates internally. If `run()` is called, gates passed.

3. **`ProducerResult` shape** — see `CONTEXT.md`. `status: Literal["ok", "skipped", "failed"]`, `reason`, `cost_usd`, `outputs`.

4. **Separate `ProducerRegistry`**, not merged into Collector Registry. Parallel `@register` decorator. `scripts/producers/base.py` houses Spec/Result/Protocol/Registry, mirroring `scripts/collectors/base.py`.

5. **Run order is registration order.** Today's order preserved: suggestions → curiosity → takes. Encoded by `scripts/producers/__init__.py` import order.

6. **`wiki produce <name> [source...]` CLI.** Manual re-run / debug / replay. Mirrors `wiki collect`. `wiki produce --list` shows registered producers + their effective gates.

7. **In-loop semantics preserved for Milestone-A.** Per-file loop still awaits each producer serially before moving on. Fire-and-forget / fan-out / deferred-batch is **Milestone-B's** decision; Milestone-A explicitly does NOT change post-pass scheduling.

8. **State key `producer_cost_total`** added to state.json. Accumulates separately from `total_cost` so the operator can distinguish SDK-compile spend from post-pass spend.

9. **`features.suggestions_source_globs` CONFIG key added.** Default `["raw/email/*.md"]`. Lifts the hardcoded `_is_email_source()` filter (suggestions/producer.py:25) out of the producer body into the declarative gate. **Config-knob change** — extends `scripts/migrations/migrate_config_keys.py` in the same commit (per CLAUDE.md hard rule; see also DECISIONS.md "Config change requires migration in same commit").

### Shape after deepening

```
scripts/producers/
    __init__.py        # imports submodules to trigger registration
    base.py            # Producer Protocol + ProducerSpec + ProducerResult + ProducerRegistry + @register
    suggestions.py     # @register class SuggestionsProducer (moved from scripts/suggestions/producer.py)
    curiosity.py       # @register class CuriosityProducer (moved from scripts/curiosity/producer.py)
    takes.py           # @register class TakesProducer (moved from scripts/facts/takes_producer.py)
    cli.py             # `wiki produce` dispatcher; mirrors collectors/cli.py
```

The existing `scripts/suggestions/`, `scripts/curiosity/`, `scripts/facts/takes_producer.py` either get re-homed under `scripts/producers/` or shrink to module aliases that re-export the new class (TBD by plan-task — depends on how many internal callers reference the current paths).

`compile.py:1272-1281` collapses to a single block, roughly:

```python
producer_results: list[ProducerResult] = []
for producer in ProducerRegistry.all():
    result = await orchestrate_producer(producer, source)  # wraps try/except + gate evaluation
    producer_results.append(result)
producer_cost_total += sum(r.cost_usd for r in producer_results)
# state-save always proceeds, regardless of producer_results statuses
```

### Test surface (what survives, what's new)

- **Survives:** end-to-end `wiki compile` on a fixture vault produces byte-identical output. The same three derivative files (suggestions, requests, takes) land in the same places with the same contents.
- **New unit tests:**
  - `test_producer_registry.py` — registration order, dedup, `all()` enumeration.
  - `test_producer_gates.py` — `enabled_config_key` and `source_glob_config_key` evaluated correctly for every producer × source-type pair.
  - `test_producer_orchestrator.py` — α-contract: a producer raising does not block state-save; `failed` ProducerResult is recorded; subsequent producers still run.
  - One regression test per producer asserting that the moved class produces byte-identical output to the legacy `maybe_X(source)` function for a fixture input.

### Deletion test

Remove the seam → cost guards, retry policy, error classification, and gate evaluation reappear in each producer body + the compile.py loop body. The current bug (curiosity crash blocking state-save) comes back. Passes.

### Subsumes

- `.ytstack/backlog/preflight-guard-rollout.md` — the three Producers' missing `assert_prompt_within_budget` calls land naturally inside the orchestrator wrapper as a pre-flight check, eliminating the per-Producer rollout.

---

## Milestone-B — compile.py orchestration

Detailed grilling deferred. Skeleton decisions:

### Three pure stages (as originally planned)

- `select_sources(criteria) → list[Path]` — pure I/O (mtime / hash-skip / role-axis filter / dry-run). No LLM.
- `compile_source(content: str, metadata: dict) → CompileResult` — pure LLM call. Owns: prompt assembly, owner-block injection, pre-flight 60kb gate, kind-unknown retry, SDK call, failure classification. No file ops, no state I/O.
- `commit_article(article: CompileResult, path: Path) → None` — pure I/O. Writes to `knowledge/<bucket>/`, updates frontmatter, atomic-replace.

### Correction (2026-05-17, post-execution) — `commit_article` is not an extraction

The "pure I/O `commit_article`" shape above was written without auditing whether the legacy code actually executes the writes Python-side. **It does not.** The SDK agent does all `knowledge/` writes inline via `Write(knowledge/**)` / `Edit(knowledge/**)` allowed_tools (or via the path-scope `can_use_tool` callback in the post-`d8a0de5` branch). Frontmatter merge, `## State` overwrite + `## Timeline` append (M005), `compiled_from:` provenance, cross-article multi-file updates per compile — all prompt-encoded, all agent-executed. Python's only knowledge/ write today is the `source-and-final` index-only branch.

A real `commit_article(article, path)` Python function would require:
1. Strip Write/Edit from `compile_source`'s allowed_tools.
2. Rewrite every substrate prompt (compile_main, compile_daily, compile_calendar, compile_health, compile_screenshots, compile_pictures, compile_memories, compile_default) to emit a structured article body — OR a multi-file manifest — as final response, not as inline tool-use side effects.
3. Build a Python parser + writer that consumes the manifest.
4. Preserve the rich multi-file capability via `CompileResult.outputs: dict[Path, FileOp]` (the single-target shape above doesn't survive).

That is a **re-architecture**, not an extraction. M018-S03 was cancelled 2026-05-17 on this finding; the deferred concept lives in `.ytstack/backlog/commit-article-manifest.md`.

**Net effect on Milestone-B:** S01 fixture-vault dropped (LLM non-determinism), S03 commit_article dropped (re-architecture), S05+S06 collapsed. M018 shipped as S02 (compile_source extraction, ✓) + S04 (post-pass lift). Future re-opening of the write-side architecture needs a fresh milestone with explicit "manifest emitter + Python writer" scope.

### Orchestrator

```python
for path in select_sources():
    result = await compile_source(path.read_text(), build_metadata(path))
    if result.ok:
        commit_article(result.article, target_path_for(path))
        await run_post_passes(path, result)   # consumes ProducerRegistry from Milestone-A
    save_state(...)
```

### Open questions (defer to Milestone-B grilling)

- **Post-pass scheduling policy.** Serial-after-file (current behavior, Milestone-A's preserved shape)? Deferred-batch (run all producers after the whole compile loop)? Per-source async-fanout?
- **Cost gates location.** The pre-flight 60kb gate (`PromptTooLargeError`) currently couples to dispatch — should it live inside `compile_source()` or before it as an orchestrator policy?
- **Lock acquisition scope.** Global compile lock (compile.lock, exists today) at orchestrator entry only, or per-stage? Almost certainly orchestrator-only.
- **`_ConsoleFormatter` (90 lines of colored per-file output).** Stays in the orchestrator (presentation concern), not pushed into stages.
- **Curiosity + takes config flags during refactor.** Disabled-by-default during dev, then flipped on at the end of regression testing — same operator-experience pattern as M011's `features.extract_takes`.

### Regression check

Byte-identical wiki output on a fixture vault, BEFORE vs. AFTER the stage split. Fixture vault TBD — likely a curated 20-source set covering each role-axis value (`source-only`, `source-and-final`, `final-only`) and each substrate-type.

### Deletion test

Remove the three-stage split → state-threading + cost-tracking + retry-policy + file-op coupling scatter back into the per-file loop. The engine's central function becomes un-testable end-to-end again (today's status). Passes hard.

---

## Sequencing summary

```
Milestone-A  →  M???-S01  Producers/base.py + Protocol + Registry + Result type
              →  M???-S02  Re-home 3 producers (suggestions, curiosity, takes)
              →  M???-S03  Wire compile.py loop to Registry + migration for source-globs CONFIG key
              →  M???-S04  `wiki produce` CLI + tests + verification on fixture vault

Milestone-B  →  M???-S01  Fixture vault for regression check
              →  M???-S02  Extract select_sources()
              →  M???-S03  Extract compile_source() (LLM-only, no I/O)
              →  M???-S04  Extract commit_article()
              →  M???-S05  Lift post-passes out of per-file loop; orchestrator emerges
              →  M???-S06  Scheduling policy decision + regression verification
```

Slice counts are estimates — `ytstack:slice-milestone` decides the final breakdown.

---

## What's NOT in scope

- **Model seam (architecture-deepening #3).** Promoted to HIGH in the 2026-05-17 walk because there are 7+ LLM call sites now. Touches compile.py and all three producers. Big interaction with this arc — but a separate milestone. If sequenced after Milestone-A, the Model seam gets to swap into the Producer's existing wrapper instead of touching three different scripts.
- **Async/sync LLM boundary** (old #10). Subsumed by the Model seam milestone, NOT by this arc.
- **Linter seam.** Lint.py absorbed the LLM-contradiction phase internally; old #4 is partially resolved. Defer until a 3rd semantic-check shape appears.
- **Dashboard consolidation, dream.py extraction, markdown helper, StateStore, datetime/tz consistency, exception handling pattern, logging config, Preprocessor seam.** All still on the architecture-deepening backlog. None block this arc.
