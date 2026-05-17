---
milestone: M018
project: llm-wiki
created: 2026-05-17T12:45:00Z
size: L
---

# M018 — Context

## Goal

`compile.py` is split into three pure stages (`select_sources`, `compile_source`, `commit_article`) plus a `run_post_passes()` orchestrator consuming the ProducerRegistry that landed in Phase 1 — so the per-file loop becomes thin, end-to-end testable, and the post-pass scheduling policy lives in one place instead of scattered through the per-file body.

## Exit criteria (revised 2026-05-17 after S03 cancellation)

1. ~~`compile.py`'s `main()` per-file loop body fits in <40 LOC~~ — **relaxed.** With S03 dropped, the knowledge/-write logic stays in the agent (via SDK Write/Edit tools); the per-file loop body shrinks via S02 + S04 but doesn't reach the <40 LOC target.
2. `compile_source()` (S02 ✓ shipped) exists as an independently unit-testable function with ≥4 tests; the SDK call is mocked.
3. Post-passes lift out of the per-file loop into `run_post_passes(source, compile_result)` which iterates `ProducerRegistry.all()` via the orchestrator that already ships from Phase 1 — no producer logic remains inline in `compile.py` (S04).
4. ~~Byte-identical regression check~~ — cancelled with S01 (LLM non-determinism). Verification reduces to manual operator smoke on lxw post-S04.
5. The 5 open questions below are CLOSED.

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
- **2026-05-17: S03 (commit_article) cancelled — knowledge/-writes stay agent-side.** Reason: S03's premise ("extract write-side logic from compile_file()") presupposes that file writes live in Python. They don't. The SDK agent does `knowledge/` writes inline via the `Write(knowledge/**)` / `Edit(knowledge/**)` allowed_tools (legacy branch) or the `can_use_tool` path-scope callback (new branch, commit `d8a0de5`). Frontmatter merge, `## State` overwrite + `## Timeline` append (M005), `compiled_from:` provenance, `knowledge/index.md` row maintenance, multi-file knowledge cross-updates within one compile — all prompt-encoded, all agent-executed.

  The producer-seam design doc (`producer-seam.md`) wrote "`commit_article(article, path)` — pure I/O" as if it were an extraction; in reality it would be a **re-architecture**: strip Write/Edit from the agent, rewrite every substrate prompt to emit a structured article body (or multi-file manifest) as final response, build a Python parser + writer that consumes that manifest. The rich agent-side multi-file capability (one transcript compile touching N entity pages with Timeline appends) does not survive a single-target `commit_article(article: str, path: Path) → None` shape unless `CompileResult` grows a `outputs: dict[Path, FileOp]` manifest field — which is a contract change the slice plan did not anticipate.

  Closing the slice is the cheaper honest call: M018 reduces to **S02 (✓ shipped) + S04 (post-pass lift)**, exit-criterion #1's `<40 LOC` per-file body target is relaxed (the body still shrinks from the LLM-call extraction; the write block stays). Future re-opening would live in a fresh milestone with explicit scope: "knowledge/-write architecture pivot — agent emits manifest, Python persists." Deferred to backlog: `.ytstack/backlog/commit-article-manifest.md` (or similar — see Out of scope below).

## Open questions

All 5 closed 2026-05-17 (see "Decisions locked" above). `ytstack:slice-milestone` is now unblocked.

## Out of scope (explicitly)

- **Model seam** (architecture-deepening #3). Big interaction, but separate milestone. Sequenced after M018 — the Model seam will swap into the orchestrator's per-stage Producer wrapper instead of touching 7+ call sites directly.
- **Async/sync LLM boundary.** Subsumed by the future Model seam milestone, NOT by M018.
- **Linter seam, Dashboard consolidation, dream.py extraction, markdown helper, StateStore, datetime/tz consistency, exception handling pattern, logging config, Preprocessor seam** — architecture-deepening backlog. None block M018.
