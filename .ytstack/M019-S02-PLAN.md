---
milestone: M019
slice: S02
project: llm-wiki
created: 2026-05-17T11:05:00Z
status: done
task_count: 5
completed_tasks: 5
---

# M019-S02 — Slice Plan

**Goal:** Inference contract end-to-end with batched-by-subscale design (R3), token-budget audit (R2) for the 5 wedge instruments, first PHQ-9 inference run persisted with embedded methodology + provenance, plus 4 additional wedge instruments (GAD-7, ASRS-v1.1, WHO-5, MEQ-19) shipped as YAML-only.

## Tasks

- [x] T01 — **R2 token-budget audit.** ✓ Done 2026-05-17. Audit-script at `scripts/reports/_engine/audit_scope.py` walks lxw substrate over instrument's declared lookback, sums tokens via 4-char/token heuristic, compares against 160K budget (200K × 80%). Results on lxw: **PHQ-9 (real, 14d) = 191 files / ~106K tokens / 33.8% headroom PASS**. **IPIP-NEO-120 synthetic stub (180d, +people-pages +takes) = 133 files / ~147K tokens / 7.8% headroom WARN** — confirms empirically that personality instruments will overflow when substrate grows another 1-2 months OR scope widens; pre-digestion layer is mandatory before they land. Outcomes documented in `.ytstack/KNOWLEDGE.md` under "M019 R2 audit". Architecture implication: batched-by-subscale interface stays in S02-T02 even though wedge fits as single-batch — it's the migration path for personality.

- [x] T02 — **`lib/inference.py` batched-by-subscale interface.** ✓ Done 2026-05-17. `BatchResult`, `ItemInference`, `EvidenceRecord`, `InferenceBatch`, `default_batches()`, `infer_batch()` + async variant. Wires the exact scope-lock composition from S01-T01 (Read/Glob/Grep + disallowed Write/Edit/NotebookEdit + permission_mode default + make_path_scope_gate([]) + prompt_stream). Default batching = one batch per subscale (PHQ-9: 1 batch; ASRS-v1.1: 2 batches Part-A/Part-B). JSON schema validated (rejects missing items / extra items). StderrCapture + log_sdk_failure pattern from compile.py.

- [x] T03 — **Inference prompt at `prompts/reports/infer_instrument.md`.** ✓ Done 2026-05-17. Scope-locked observer/informant framing, ${instrument_*}/${items_block}/${substrate_block}/${batch_label}/${today} placeholders, JSON-schema-required output, `substrate_inferable: false` items must return null answer + zero confidence, evidence citations required with verbatim quotes. `EvidenceRecord` lives in lib/inference.py (collapsed T03 — no separate provenance.py needed, dataclass + JSON adapter is sufficient).

- [x] T04 — **First live PHQ-9 inference end-to-end.** ✓ Done 2026-05-17. `scripts/reports/_engine/runner.py` orchestrates load → scope resolution → prompt render → infer_batch → score → persist. Live-tested on lxw substrate: **191 files, 11.5K prompt chars, ~96s, $0.17, 4/9 items inferred at high confidence (exactly the 4 substrate_inferable=true ones)**. Coverage 44.4% < 80% bandable threshold → no band emitted (correctly partial). Report markdown at `/tmp/m019-s02-t04-test/phq-9.md` validated: frontmatter complete (instrument/version/run_ts/score/band/coverage/scope/model_id/prompt_version/cost), per-item table with Q3 sleep @0.82 confidence + 7 evidence citations from Oura + voice notes, embedded methodology block (items.yaml + cutoffs.yaml + instrument.yaml + rendered prompt + scope-resolved substrate paths). Architecture empirically validated.

- [x] T05 — **4 more wedge instruments.** ✓ Done 2026-05-17. GAD-7 / ASRS-v1.1 / WHO-5 / K6 (substitute for MEQ-19 — MEQ has heterogeneous per-item scales that wedge likert architecture doesn't yet support; K6 fills same wedge role with single-scale clinical screen + published clinical cutoffs, MEQ deferred to post-wedge after per-item-scale support lands). All public domain / free-research, items verbatim from authoritative sources, substrate_inferable curated per item. ASRS-v1.1 modeled as Part-A (6) + Part-B (12) subscales; ASRS continuous-sum bands are extrapolation (note in cutoffs.yaml), full Part-A-threshold-counting scoring deferred to post-wedge custom scoring.py. Inferable coverage ceiling per instrument: PHQ-9 44%, GAD-7 57%, ASRS-v1.1 33%, WHO-5 80% (highest), K6 33% (lowest). 31 new unit tests in tests/reports/test_instrument_validity.py: load + range + uniform-zero + uniform-max + 4 published clinical thresholds (PHQ-9 10+ / GAD-7 10+ / WHO-5 ≤12 / K6 13+) + ASRS subscale structure + substrate_inferable curation completeness + per-instrument inferable-count pin (catches silent drift).

## Done when

- R1 outcome (from S01) referenced; either path forward (allowlist OR callback) chosen for `lib/inference.py`.
- R2 token-budget audit documented; all 5 wedge instruments confirmed under 200K.
- R3 batched-by-subscale interface shipped with at least one mock-tested multi-subscale call.
- First real PHQ-9 inference run persisted to disk with embedded methodology + provenance.
- All 5 wedge instruments validate + score against synthetic input.
- `uv run pytest tests/reports/ -v` green.

## Notes

(Operator likely lands first surprises here — confidence calibration vs. operator's lived sense, evidence-path quality, etc. Promote to DECISIONS.md if architecture-affecting.)
