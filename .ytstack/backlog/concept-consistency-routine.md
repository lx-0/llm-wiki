# Autonomous concept-consistency routine ("concept dream-cycle")

**Status:** CONCEPT (Phase 1 of `llm-wiki-change`) — awaiting operator review. No code yet.
**Captured:** 2026-05-22

## Why

The brain has a strong *detection* layer and an *entity* re-synthesis loop, but **no autonomous loop that keeps `knowledge/concepts/` consistent — with the hard facts and with each other — and adapts them.** Today:

- `lint.check_facts_violations` flags concepts that contain a fact's `negation_terms` → operator must run `wiki correct apply` per fact.
- `lint.check_contradictions` (LLM) finds concept↔concept contradictions → report only.
- `dream.py` re-synthesizes **entities** (people/projects/areas), never concepts.
- Facts only re-touch a concept when its *source* is re-compiled (hash-diff) — a new fact does not reach already-compiled concepts.

So fact-violations and drift accumulate silently; closing the loop is manual. This routine closes it under **strict, auditable policies**.

## What

A **signal-driven, cost-capped, cooldown-gated autonomous routine** that:

1. **Collects signals** from the existing detectors (no new detection logic).
2. **Selects** the highest-priority flagged concepts under a per-run budget.
3. **Reconciles** each concept under a strict policy — *auto-fix* the safe class, *propose-only* the judgment class.
4. **Logs + stamps** every change; everything is git-reversible.

It is "dream-cycle for concepts," but **signal-driven** (only touches a concept a detector flagged) rather than a blind sweep.

## Strict policies (the core — these are the guardrails that make autonomous writes safe)

1. **No signal → no edit.** A concept is only touched if a detector flagged it this run. No blind rewrites.
2. **Authority hierarchy: hard facts > compiled concepts.** The routine may rewrite a concept to MATCH a fact; it may NEVER weaken, delete, or contradict a fact.
3. **Tiered autonomy by issue class:**
   - `fact_violation` (concept contradicts a hard fact) → **AUTO-CORRECT.** Direction is unambiguous (fact is authority).
   - `contradiction` (concept↔concept, LLM) → **PROPOSE-ONLY.** Never auto-pick a winner — emit a `qa/`-style flagged note / dashboard item for the operator. Auto-rewrite risks erasing the correct side.
   - mechanical schema (missing `domain:` tag, etc.) → **AUTO-FIX** (deterministic, already `auto_fixable` in lint).
   - quality (sparse / stale / weak connections) → **PROPOSE-ONLY** (content judgment).
4. **Write-scope lock:** writes restricted to `knowledge/concepts/**` (ideally only the target file) via the PreToolUse `make_path_scope_hook` — NOT `correct_apply`'s broad `acceptEdits`. **No Bash, no raw/, no daily/, no facts/.**
5. **Minimal diff, append-/edit-only.** Never delete an article. Preserve frontmatter (`compiled_from`, `author`, `domain`, `type`). Backup before edit (reuse `correct_apply._backup`).
6. **Idempotent.** Re-running on an already-reconciled concept is a no-op (stamp `last_reconciled_at:` + a content check).
7. **Hard cost caps** (per-concept + per-run) and **cooldown** — reuse dream.py's exact knobs.
8. **Provenance + reversibility:** one `knowledge/log.md` line per change; git is the undo. A `reconciled_from:`/`last_reconciled_at:` frontmatter stamp.
9. **Default OFF + dry-run-first.** `features.concept_reconciliation: bool = False`. Ships dry-run; operator flips it on after reviewing a dry-run diff.
10. **Provider: Claude SDK only** for the rewrite (per `feedback_no_silent_provider_fallback`); bounded `max_turns`; never read a >25k-token target (the health-rollup lesson) — concepts are small, but guard anyway.

## How it integrates (low-hanging fruits — reuse, then extend)

| Reuse | From | Role in the routine |
|---|---|---|
| Structured issues (`issue()` dicts: severity/check/file/auto_fixable) | `lint.py` (21 checks) | **Signal source.** Import lint, run the relevant checks, group issues by concept file. No new detection. |
| `check_facts_violations` (812) + `check_contradictions` (1031) | `lint.py` | The two primary signals (fact-authority + drift). |
| Candidate selection (overdue), `is_within_cooldown` (263), per-entity + per-run cost caps, `dream_priority` precedence, piggyback wiring, dry-run, cost pre-flight | `dream.py` | **Scheduler + selection + budget machinery.** Extend the same pattern to a "concept" target class. |
| Scoped agentic write, `_backup` (69), frontmatter split/write (48/64) | `facts/correct_apply.py` | **Write primitive** — but TIGHTEN scope to `knowledge/concepts/**` via the PreToolUse hook. |
| `make_path_scope_hook` + `tools`/`allowed_tools` discipline | `compile_stages/compile.py` + `core/sdk_helpers.py` | **Write-scope lock** (policy #4). |
| `${facts_md}` hard-facts block | compile prompts | The authority the rewrite reconciles against. |
| Piggyback (cooldown-gated, after compile) | `flush.py` `_LEGACY_PIGGYBACK_COMMANDS` | **Autonomous trigger** — new `concept_reconcile` piggyback, default off. |

**Two build shapes (open decision A):** (i) extend `dream.py` with a `concept` target class (max reuse, one module owns "cross-time re-synthesis"); (ii) a sibling `reconcile.py` that imports dream's helpers. Lean: (i).

## Edge cases & failure modes

- **Concept↔concept contradiction with no fact to arbitrate** → propose-only (policy #3), never auto-resolve.
- **Fact itself ambiguous / disambiguation-status** → skip auto-correct, propose (only `negation`-status facts with clear terms auto-correct).
- **Churn / oscillation** (routine rewrites A, next run flags A again) → cooldown + idempotency stamp + "no signal after edit = stop."
- **Cost runaway** → per-run cap aborts the sweep mid-list (dream pattern).
- **Bad rewrite** → git-reversible + `_backup` + dry-run-first rollout; auto-class limited to the unambiguous fact-authority case.
- **Provenance bloat** (the health-rollup lesson) → one log line per change, NOT a growing list in a shared article; stamp lives in the concept's own frontmatter.
- **Provider down** → Claude SDK only; if unreachable, skip the run (no partial state).
- **Concept also serves as a policy article** (e.g. `health-rollup-intake-format`) → exclude `compile_role: source-and-final` / hand-curated concepts from auto-correct (respect the existing role axis).

## Decisions — LOCKED 2026-05-22 (operator: "nimm deine Empfehlungen")

- **A. Build shape — REVISED in Phase 2.** Original rec was "extend `dream.py`"; **rejected on inspection** — dream is entity-corpus + State/Timeline shaped, not reconciliation-shaped. The real primitive is **`facts/correct_apply.py`** (it already does fact→article reconciliation via Claude SDK), plus `lint` for signals. Build = a thin orchestrator `scripts/reconcile.py` that drives a **new strict mode of `correct_apply`** over the facts that `lint` flags. Less new code than the dream route.
- **B. Autonomy tier — confirmed.** AUTO: `fact_violation` + mechanical `auto_fixable` schema. PROPOSE-ONLY: concept↔concept `contradiction` + quality.
- **C. Cadence/caps/pilot — confirmed.** Default OFF + dry-run-first IS the pilot gate. Knobs (proposed defaults): `scheduling.concept_reconcile_cooldown_days: 14`, `limits.concept_reconcile_max_cost_per_run_usd: 0.50`, `limits.concept_reconcile_per_fact_max_cost_usd: 0.10`.
- **D. Propose-only channel — confirmed.** Reuse the existing lint→`_dashboard-lint` surface (those warnings already render) + a per-run summary line in `knowledge/log.md`. No new channel.

## Verified integration plan (Phase 2 — exact changes)

1. **`scripts/facts/correct_apply.py`** — add `strict: bool = False` to `apply()`. When strict:
   - `allowed_tools=["Read","Glob","Grep","Write","Edit"]` (NO Bash) + `hooks={PreToolUse: make_path_scope_hook([KNOWLEDGE_DIR/"concepts"])}` + `permission_mode="default"` (the compile.py pattern), `max_turns` from a new knob (~15), pre-flight cost cap.
   - Render a new tight prompt `prompts/reconcile_concept.md` (minimal-diff, ONLY edit the flagged concept, reconcile against the fact, never touch frontmatter provenance). Existing `wiki correct apply` path (strict=False) is **unchanged**.
2. **`scripts/reconcile.py`** (new) — orchestrator: import `lint`, run `check_facts_violations()` (+ optionally `check_contradictions()` for the propose digest); group fact_violations by fact slug; for each fact under cooldown (`applied:`/new `last_reconciled:` stamp) + per-run cost cap, `await correct_apply.apply(slug, strict=True)`; write one `knowledge/log.md` summary line (auto-fixed N, proposing M); `--dry-run` default-safe. CLI: `wiki reconcile [--dry-run] [--limit N]`.
3. **`scripts/core/config.py`** — `features.concept_reconciliation: bool = False` + the 3 limits/scheduling knobs above. **+ same-commit migration** in `migrations/migrate_config_keys.py` (CLAUDE.md hard rule).
4. **`scripts/flush.py`** — new `_LEGACY_PIGGYBACK_COMMANDS["concept_reconcile"] = ["reconcile.py", "--limit", "{max_per_run}"]`, default cooldown long, gated by the feature flag (skip if off).
5. **`wiki`** dispatcher — `reconcile)` subcommand → `_run_script reconcile.py`.

**Does not break existing flows:** every change is additive + flag-gated-off. `correct_apply` strict defaults False (existing CLI untouched); lint imported read-only; piggyback default off; config additive + migrated.
