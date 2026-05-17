---
milestone: M021
project: llm-wiki
created: 2026-05-17T14:10:00Z
size: L
---

# M021 — Context

## Goal

Unify all 7+ LLM call sites (Claude SDK + Ollama) behind a single `scripts/llm.py` interface so retry policy, schema handling, failure classification, async/sync bridging, and KNOWLEDGE.md gotchas consolidate in one place instead of being copy-pasted across the engine.

## Exit criteria

1. `scripts/llm.py` (or `scripts/adapters/llm/`) ships with `generate_text(prompt, model=None, temperature=None, timeout=None)`, `generate_structured(prompt, schema, model=None)`, `generate_vision(image_path, prompt, model=None)`. Dispatcher resolves backend from CONFIG or explicit `model_kind=` hint.
2. All 7+ existing LLM call sites consume the new interface: `compile_stages/compile.py` (the heaviest — SDK + retry ladder lives here today), `curiosity/producer.py`, `suggestions/producer.py`, `facts/takes_producer.py`, `review-wiki.py`, `ingest-html.py`, and the vision collectors (`scan_screenshots.py`, `scan_youtube.py`, `pictures.py`, `voice.py`).
3. Ollama calls wrapped with `asyncio.to_thread()` — the async/sync mismatch (Claude SDK async, Ollama sync) stops blocking the event loop. Curiosity producer no longer freezes compile-loop fan-out on long Ollama calls.
4. KNOWLEDGE.md gotchas consolidated into the seam: Ollama `format:json` is insufficient (need explicit schema); JSON-schema vs tool-use schema variance; vision-OCR temperature defaults; rate-limit + cli_crash classification (already partly in `core/sdk_helpers.py:FailureClass`). All in one module's docstring + code, not scattered across call sites.
5. Full test suite stable (no new failures vs pre-milestone baseline). SDK calls mockable through the new seam (`llm.generate_text` swappable in tests).

## Size

L — see `M021-ROADMAP.md` for slice breakdown. Sequenced as: (1) llm.py base API + Claude backend, (2) Ollama backend + async bridging, (3) migrate producers + compile_source, (4) migrate vision + auxiliary callers, (5) cleanup + dead-helper removal + docs.

## Source materials

- **Architecture-deepening backlog:** `.ytstack/backlog/architecture-deepening.md` #3 — full design rationale, graduated MEDIUM → HIGH 2026-05-17 (7+ call sites crossed the threshold).
- **Existing infrastructure:** `core/sdk_helpers.py` (Claude side: StderrCapture, log_sdk_failure, FailureClass classifier, assert_prompt_within_budget, make_path_scope_gate, prompt_stream); `core/ollama_client.py` (Ollama side: sync httpx wrapper).
- **Sequenced after:** Producer-seam (Phase 1 ✓, Phase 2/M018 ✓). M021 is the third milestone in the architecture-deepening arc.

## Decisions locked in discuss phase

- **2026-05-17: Single-process async interface.** Claude SDK is async-native; Ollama gets wrapped via `asyncio.to_thread()` for parity. The alternative (two parallel sync + async APIs) was considered + rejected because every current async caller (`compile_source`, producers, curiosity) would need explicit branch on backend kind. Single-async-interface keeps callers shape-agnostic.

## Open questions

(Items to resolve during slicing. Close as decisions land in the list above.)

1. **Module location.** `scripts/llm.py` (single file) vs `scripts/adapters/llm/` (sub-package mirroring `scripts/adapters/mailbox/` with `base.py` + `claude.py` + `ollama.py`)? Sub-package gives a Protocol seam parallel to Reader/Filter; single file is YAGNI until a 3rd backend lands. Lean toward sub-package given the design says "centralized retry + cost estimation + failure classification" — that's enough internal structure to warrant the split. **Close before S01.**
2. **Schema shape.** Pydantic `BaseModel` (used in some collectors today) vs raw JSON schema dict (Ollama-native) vs Claude tool-use schema dict. Three variants in play. Pick one canonical for `generate_structured(schema)` and adapt internally. **Close before S03 (producer migration).**
3. **Failure-classification scope.** `FailureClass` today is Claude-SDK-shaped (kind: rate_limit, cli_crash, auth, model, network, timeout, unknown). Ollama failure modes (HTTP timeouts, schema-non-honor, model-not-pulled) overlap partially. Unify under one FailureClass with backend-kind discriminator? Or keep two? **Close before S02 (Ollama backend).**
4. **Cost estimation.** Claude SDK reports actual cost in `ResultMessage`. Ollama doesn't. The seam's return shape needs to handle "cost known" (Claude) and "cost unknown / local" (Ollama). Probably `cost_usd: float | None`, with None meaning "local, no cloud spend." **Close before S01.**
5. **Migration order.** Compile_source is the heaviest caller (200+ LOC of LLM-call body, already extracted into compile_stages/compile.py). Doing it FIRST surfaces the most pain; doing it LAST means smaller callers prove the interface first. Lean toward compile_source FIRST in S03 — it's where the gotcha-knowledge lives, so the migration test is whether the interface absorbs that knowledge cleanly. **Close before S03.**

## Out of scope (explicitly)

- **Caller body refactors beyond the LLM-call swap.** If a producer has spaghetti around its `query()` call that's not related to the call itself, leave it. M021 swaps the call site, doesn't tidy adjacent code.
- **Multi-provider support beyond Claude + Ollama.** No OpenAI, OpenRouter, local llama.cpp, etc. The seam shape SHOULD admit them (that's the whole point), but actually wiring a third backend is a separate future milestone.
- **Streaming output API.** Today no caller streams partial output (compile_source consumes the SDK's `async for` but only for ResultMessage capture, not progressive emission). The seam can stay one-shot (`generate_text → str`).
- **Tool-use API.** Claude SDK supports tool use; Ollama doesn't (uniformly). `generate_text` / `generate_structured` are no-tool-use; tool-use stays as a direct SDK call in compile_source where it's needed.
- **`commit_article` / agent-disarm.** That's the deferred re-architecture from M018-S03 cancellation; see `.ytstack/backlog/commit-article-manifest.md`. Orthogonal to the Model seam.
