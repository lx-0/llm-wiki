---
milestone: M021
project: llm-wiki
size: L
created: 2026-05-17T14:10:00Z
status: planned
total_slices: 5
completed_slices: 0
---

# M021 Roadmap

**Goal:** Unify all 7+ LLM call sites (Claude SDK + Ollama) behind a single `scripts/llm.py` (or `scripts/adapters/llm/`) interface so retry policy, schema handling, failure classification, async/sync bridging, and KNOWLEDGE.md gotchas consolidate in one place.

**Exit criteria:**
1. `llm.generate_text / generate_structured / generate_vision` exist; dispatcher resolves backend from CONFIG or explicit `model_kind=` hint.
2. All 7+ current LLM call sites consume the new interface (compile_source, 3 producers, review-wiki, ingest-html, 4 vision collectors).
3. Ollama wrapped with `asyncio.to_thread()` — async/sync mismatch resolved, curiosity no longer blocks event loop.
4. KNOWLEDGE.md gotchas (Ollama format:json insufficient, schema variance, vision-OCR quirks) consolidated into the seam.
5. Full suite stable, no new failures vs pre-M021 baseline.

## Slices

Slice detail lives in per-slice `M021-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [ ] S01 -- (to be planned) — `llm/` package base + Claude backend + open-question closures (Q1 location, Q4 cost shape)
- [ ] S02 -- (to be planned) — Ollama backend + `asyncio.to_thread` bridging + Q3 (FailureClass unification)
- [ ] S03 -- (to be planned) — Migrate compile_source + 3 producers (curiosity, suggestions, takes); Q2 (schema shape) + Q5 (migration order) closure
- [ ] S04 -- (to be planned) — Migrate vision collectors (scan_screenshots, scan_youtube, pictures, voice) + auxiliary text callers (review-wiki, ingest-html)
- [ ] S05 -- (to be planned) — Cleanup: dead helpers in `core/sdk_helpers.py` + `core/ollama_client.py`, KNOWLEDGE.md gotcha consolidation in seam docstring, backlog flip, memory pointer, STATE update

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality. S01+S02 build the seam; S03+S04 migrate callers; S05 closes out. Open questions Q1+Q4 close before S01, Q3 before S02, Q2+Q5 before S03.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed.
- Update `completed_slices` count.
- On milestone completion, flip `status: planned` → `status: done`.
- If new slices are added during execution, bump `total_slices`.
