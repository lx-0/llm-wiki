# Token-usage accounting — tokens per (provider, model), not a dollar currency

**Status:** BUILDING 2026-05-23 (operator-directed pull-forward of M021's "cost shape" question). Concept->Verify done; implementing the ledger + wiring. Follows the `llm-wiki-change` 5-phase process, NOT a ytstack milestone (M021/M025 are parallel-owned -- this is a focused arc that *feeds* M021's model seam, doesn't re-slice it).

## Why (the premise the operator challenged)

The engine tracked LLM usage as **US dollars** -- pre-flight `prompt_chars -> $` estimates plus post-hoc `ResultMessage.total_cost_usd`, gated by USD caps. That model is wrong here:

- **Claude runs on a subscription.** There is no per-call dollar charge; `total_cost_usd` reflects an API rate-card that does not apply. Gating on it is gating on a fiction.
- **Ollama is local.** Always `$0`. A dollar cap is meaningless; the only real cost is wall-clock + local compute.
- **Multiple providers can't share one dollar currency.** A single USD figure conflates a subscription, a free local server, and (potentially, later) a true pay-per-token API. They are not commensurable.

The honest usage unit is **tokens, keyed by `(provider, model)`**. Dollars only ever appear for a *true pay-per-token provider* via an explicit rate-card -- and none exists in the engine today.

## What

A central usage ledger + provider-appropriate gates.

### Ledger (`scripts/core/usage.py`)

- `provider_for_model(model)` -> `"claude" | "ollama"` -- inferred from the model id (`claude*`/`anthropic*` -> claude; everything else -> the local Ollama server). Extensible to real pay-per-token providers later.
- `UsageLedger` -- accumulates `(provider, model) -> {input_tokens, output_tokens, calls}` for one process/run.
  - `record(model, input_tokens, output_tokens, calls=1, provider=None)` -- the one method call sites use.
  - `summary_line()` -- `claude/claude-opus-4-7 12.3K in / 4.1K out / 3 calls | ollama/gemma4:e4b ...`.
  - `persist(day=None)` -- merge the run's totals into `state/usage.json`, bucketed `date -> "<provider>:<model>" -> {...}`, under an `fcntl` lock (parallel compile/flush sessions write concurrently -- same lock discipline as `compile.lock` / dashboard refresh).
- `LEDGER` -- a process-global default instance.

### Capture points (where tokens come from)

- **Ollama** -- centralized in `core/ollama_client.py`. `chat()` reads the `/v1` `usage.{prompt_tokens,completion_tokens}`; `chat_schema()`/`chat_vision()` read the native `/api/chat` `prompt_eval_count`/`eval_count`. The client records into `LEDGER` automatically -- **no caller signature changes**.
- **Claude** -- each SDK call site already accumulates `AssistantMessage.usage.{input_tokens,output_tokens}` in its message loop. Add one `LEDGER.record(...)` after the loop. (When the M021 model seam wraps `query()`, this moves into the wrapper and the per-site calls disappear.)

### Gates (replace the USD caps)

USD caps were doing two different jobs; split them by what they actually protect:

| Old USD cap | Replacement |
| --- | --- |
| `compile_max_cost_per_file_usd` ($2.50) | `compile_max_tokens_per_file` (token ceiling from `ResultMessage`/usage; abort batch on overrun, same control flow) |
| `dream_entity_max_cost_usd` ($2.0) | structural: prompt-char preflight stays as a **size** guard; per-entity token ceiling from real usage |
| `dream_cycle_max_cost_per_run_usd` ($5.0) | `dream_cycle_max_tokens_per_run` (cumulative real tokens; stop sweep on overrun) |
| `concept_reconcile_per_fact_max_cost_usd` ($0.10) | **structural** `concept_reconcile_max_files_per_fact` (skip a fact violating > N concept files -> manual review; the dollar pre-estimate is dropped -- unreliable for an agentic loop AND meaningless under subscription) |
| `concept_reconcile_max_cost_per_run_usd` ($0.50) | `concept_reconcile_max_facts_per_run` + cumulative token ceiling |

Pre-flight `prompt_chars -> $` estimates (`correct_apply._estimate_cost_usd`, `dream.estimate_cost_usd`) are removed. Prompt-**size** preflight (chars) is kept where it already guards context-overflow -- a real, provider-independent failure mode, distinct from cost.

All config changes carry a same-commit `migrate_config_keys.py` extension (hard rule). USD keys are removed outright (no soft deprecation -- internal-user-only project).

## Blast radius (verified 2026-05-23)

- Capture: `core/ollama_client.py` (3 fns) + `compile_stages/compile.py`, `dream.py`, `facts/correct_apply.py`, `reports/_engine/lib/{inference,analyst}.py`.
- Caps/config: `core/config.py` (6 USD knobs) + `migrations/migrate_config_keys.py` + `config.example.yaml`.
- Display-only (USD strings -> token strings): `analyze.py`, `study.py`, `producers/cli.py`, `compile.py` summary line.
- `reconcile.py` gate swap (USD -> structural).

## Edge cases

- **`total_cost_usd` absent/zero** under subscription -- already the reason this exists; the ledger never reads it.
- **Ollama unreachable** -- no usage to record; ledger stays empty for that key. Fine.
- **Parallel writers** to `state/usage.json` -- `fcntl` lock + read-merge-write.
- **Unknown model id** -> defaults to `ollama` provider (local). A real pay-per-token provider must be added explicitly to `provider_for_model` (and only then does a rate-card/dollar mapping enter).
- **Idempotency** -- the ledger is observability, not control flow; a missed/double record degrades the report, never correctness.

## Relation to M021 (model seam)

This is M021's **"cost shape"** open question, answered: usage = tokens per provider/model. `core/usage.py` is the accounting half of the seam; `scripts/llm.py` (the call-wrapping half, M021) will fold the per-site `LEDGER.record(...)` calls into the wrapper. Built standalone now so it doesn't block on M021's slicing (parallel-owned).

## Related

- `.ytstack/M021-CONTEXT.md` (model seam; cost-shape question)
- `.ytstack/DECISIONS.md` 2026-05-23 (this decision, canonical)
- `core/ollama_client.py`, `compile_stages/compile.py`, `dream.py`
