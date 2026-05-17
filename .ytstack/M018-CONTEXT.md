---
milestone: M018
project: llm-wiki
created: 2026-05-17T12:45:00Z
size: L
---

# M018 — Context

## Goal

`compile.py` is split into three pure stages (`select_sources`, `compile_source`, `commit_article`) plus a `run_post_passes()` orchestrator consuming the ProducerRegistry that landed in Phase 1 — so the per-file loop becomes thin, end-to-end testable, and the post-pass scheduling policy lives in one place instead of scattered through the per-file body.

## Exit criteria

1. `compile.py`'s `main()` per-file loop body fits in <40 LOC and contains zero LLM calls, zero file writes, zero state-save logic — only orchestration of the three stages + the post-pass orchestrator.
2. `select_sources()`, `compile_source()`, `commit_article()` exist as independently unit-testable functions; each has ≥3 tests; the first two are pure (no I/O / no LLM respectively).
3. Post-passes lift out of the per-file loop into `run_post_passes(source, compile_result)` which iterates `ProducerRegistry.all()` via the orchestrator that already ships from Phase 1 — no producer logic remains inline in `compile.py`.
4. Regression check: `wiki compile` on a curated fixture vault (≥1 sample per role-axis value + ≥1 per substrate-type) produces byte-identical `knowledge/` output BEFORE vs. AFTER the refactor.
5. The 5 open questions below are CLOSED (lifted to "Decisions locked" with date + reason) before the orchestrator-cut slice (S05) starts.

## Size

L — see `M018-ROADMAP.md` for slice breakdown.

## Numbering note

Milestone IDs M008–M017 were used in commits + memory pointers for ad-hoc arcs (areas-bucket, author-attribution, reliability bundle, takes, connection-quality, domain-frontmatter, dream-cycle MVP, sampled-activation, dream-priority). None of those shipped through `plan-milestone` — they have no ROADMAP/CONTEXT files. M018 is the next *formally-planned* milestone; the numbering jump preserves the historical IDs in memory + git history.

## Source materials

- **Design doc:** `.ytstack/backlog/producer-seam.md` (Milestone-B section, lines 89–124) — locked decisions on the three-stage cut + orchestrator shape + regression-check strategy.
- **Phase 1 already shipped:** ProducerSpec/Result/Protocol/Registry + 3 wrappers (suggestions/curiosity/takes) + `evaluate_and_run` orchestrator + `compile.py` per-file post-pass loop wired to Registry + `wiki produce` CLI. Commits `3f98d19`, `ea05916`, `32dab60`, `4e47ff4`, `e730d26`, `49849ad`.
- **Subsumes:** `.ytstack/backlog/preflight-guard-rollout.md` — the orchestrator's wrapper is the natural home for the missing `assert_prompt_within_budget` calls.

## Decisions locked in discuss phase

- **2026-05-17: Q1 — Post-pass scheduling = serial-after-file.** Reason: Phase 1 preserved this shape; introducing `defer` / `fanout` modes now is YAGNI (no producer needs them today). Locks the operator-experience: a slow curiosity Ollama call still delays the next file, but cost gates + per-file state-save semantics stay intact. Future spec-level `defer: bool` is a strictly-additive escape hatch when a real-world producer demands it.
- **2026-05-17: Q2 — Pre-flight 60kb gate (`PromptTooLargeError`) lives inside `compile_source()`.** Reason: the gate is a "can this LLM call succeed?" check on the prompt about to be built — that's `compile_source()`'s domain. The orchestrator catches the raised exception → marks the file failed → moves on. Keeps `compile_source()` the single owner of LLM-call viability.
- **2026-05-17: Q3 — Compile lock = orchestrator entry only.** Reason: per-stage locks would slow execution without preventing real races (the engine runs serially within one process; cross-process is what `STATE_DIR/compile.lock` already covers). Confirmed.
- **2026-05-17: Q4 — `_ConsoleFormatter` stays in the orchestrator module** (top of `compile.py`, alongside `main()` + the per-file loop). Reason: presentation concern, not stage concern. The stages emit raw `log.info`/`log.error` lines; the formatter shapes them. Confirmed.
- **2026-05-17: Q5 — Curiosity + takes stay live throughout the refactor.** Reason: Phase 1 preserved exact behavior; M018's stage extractions are byte-identical or they don't ship. Toggling feature flags during dev would mask regressions in producer output instead of surfacing them. Operator daily compile keeps producing knowledge-gap requests + takes during M018 work. (M011-style ship-gated flag was for a feature-new substrate; this is a refactor of code that already produces material.)

## Open questions

All 5 closed 2026-05-17 (see "Decisions locked" above). `ytstack:slice-milestone` is now unblocked.

## Out of scope (explicitly)

- **Model seam** (architecture-deepening #3). Big interaction, but separate milestone. Sequenced after M018 — the Model seam will swap into the orchestrator's per-stage Producer wrapper instead of touching 7+ call sites directly.
- **Async/sync LLM boundary.** Subsumed by the future Model seam milestone, NOT by M018.
- **Linter seam, Dashboard consolidation, dream.py extraction, markdown helper, StateStore, datetime/tz consistency, exception handling pattern, logging config, Preprocessor seam** — architecture-deepening backlog. None block M018.
