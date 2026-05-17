---
milestone: M019
slice: S02
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M019-S02 — Slice Plan

**Goal:** Inference contract end-to-end with batched-by-subscale design (R3), token-budget audit (R2) for the 5 wedge instruments, first PHQ-9 inference run persisted with embedded methodology + provenance, plus 4 additional wedge instruments (GAD-7, ASRS-v1.1, WHO-5, MEQ-19) shipped as YAML-only.

## Tasks

- [ ] T01 — **R2 token-budget audit (mandatory).** Probe-script `scripts/reports/_engine/audit_scope.py` that, for each instrument's declared scope (lookback windows + source-type filters + keyword filters), resolves the substrate-file list against current lxw substrate, sums tokens via `len(text)/4` heuristic + opt-in `tiktoken` for accuracy, reports per-instrument total + delta-vs-200K-budget. Run against the 5 wedge instruments (small scope, expected pass) AND against a stub IPIP-NEO-120-scope (large scope, expected fail) to confirm the audit catches overflow. Document outcomes in KNOWLEDGE.md under "M019 R2 audit 2026-05-17". If any wedge-instrument scope exceeds 200K → narrow lookback or split substrate before T02.

- [ ] T02 — **`lib/inference.py` batched-by-subscale interface (R3 design).** Accepts `(instrument, scope_resolution, batching_strategy)`. Default batching for single-subscale instruments = one batch (all items in one call). For multi-subscale: caller-provided batch-grouping (e.g. IPIP-NEO Big Five domains → 5 batches). Wraps `claude_agent_sdk.ClaudeSDKClient` with `StderrCapture` + `classify_failure` mirror of `scripts/compile.py`. Uses `core.sdk_helpers.make_path_scope_gate(['reports/'])` + `prompt_stream(...)` per the 2026-05-17 callback-gate decision (DECISIONS.md). Respects the three constraints: Write/Edit NOT in `allowed_tools`, `permission_mode != 'acceptEdits'`, AsyncIterable prompt. Returns `BatchResult{items: dict[item_id, ItemInference], elapsed_ms, model_id, prompt_version}`. Unit-tests with mock SDK client + golden JSON outputs (5 items happy path + degraded confidence + null-answer for `substrate_inferable: false`).

- [ ] T03 — **`lib/provenance.py` + inference prompt.** Provenance dataclass: `EvidenceRecord{file: str, line: int | None, quote: str, weight: float}`. Persistence as JSON-blob within the per-item structured response. Prompt at `prompts/reports/infer_instrument.md` — scope-locked system prompt with placeholders for `${instrument_items_yaml}`, `${substrate_excerpt}`, `${batching_hint}`. Output-schema (JSON) returns `items: {id: {answer, confidence, evidence: [EvidenceRecord], reasoning}}`. Per the existing memory `feedback_prompts_in_prompts_folder` — prompt lives in `prompts/`, never inline. Unit-test that prompt-rendering produces a valid JSON-schema-compliant template instance.

- [ ] T04 — **First end-to-end PHQ-9 inference run.** Wire scope-resolver + lib/inference + lib/provenance into a `wiki report phq-9 --ad-hoc` invocation that: (a) resolves PHQ-9 scope against current vault substrate, (b) builds the inference prompt, (c) calls Claude SDK, (d) validates JSON output, (e) persists single run to `reports/_adhoc/<timestamp>/phq-9.md` with embedded methodology block (items + scoring + cutoffs + model-ID + prompt-version + scope-spec + per-item evidence inline). Live-test on lxw substrate (after T01 confirms scope fits). Verification: report file readable, score+band computed, evidence-paths verbatim-grep-findable in source files.

- [ ] T05 — **4 more wedge instruments (YAML-only):** `gad-7/v1.0.0/`, `asrs-v1.1/v1.0.0/`, `who-5/v1.0.0/`, `meq-19/v1.0.0/` — each with `instrument.yaml` + `items.yaml` (items transcribed from PD authoritative source, per-item `substrate_inferable` curated 1 hour per instrument) + `cutoffs.yaml`. ASRS-v1.1 has 6-item Part A + 12-item Part B split — modeled as two subscales within one instrument. Per-item scope-spec mirrors PHQ-9 patterns. Verification: `uv run pytest tests/reports/test_instrument_validity.py` covers all 5 wedge instruments load + score against synthetic answer arrays.

## Done when

- R1 outcome (from S01) referenced; either path forward (allowlist OR callback) chosen for `lib/inference.py`.
- R2 token-budget audit documented; all 5 wedge instruments confirmed under 200K.
- R3 batched-by-subscale interface shipped with at least one mock-tested multi-subscale call.
- First real PHQ-9 inference run persisted to disk with embedded methodology + provenance.
- All 5 wedge instruments validate + score against synthetic input.
- `uv run pytest tests/reports/ -v` green.

## Notes

(Operator likely lands first surprises here — confidence calibration vs. operator's lived sense, evidence-path quality, etc. Promote to DECISIONS.md if architecture-affecting.)
