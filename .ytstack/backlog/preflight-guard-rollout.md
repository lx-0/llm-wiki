# Pre-flight prompt-size guard — roll out to the remaining LLM scripts

**Priority:** P2 — defense-in-depth, not a live bug. The root-cause fixes (compact index at every LLM call site) already removed the known overflow triggers; this is the belt to the existing braces.

**Origin:** 2026-05-14, commit `6957959`. `sdk_helpers.assert_prompt_within_budget(prompt_chars, limit, *, label, breakdown)` was added and wired into `query.py` only. Context overflow can't be classified after the fact — empty stderr, variable timing → `classify_failure` returns `kind=unknown` — so the only reliable catch is a pre-flight `len(prompt)` check. See DECISIONS.md "2026-05-14: Pre-flight prompt-size guard".

## Scope

Wire `assert_prompt_within_budget` into the other three LLM-prompt call sites — same helper, ~3 lines each (build prompt → guard → SDK call):

- `compile.py` — `compile_file()` builds the largest prompts (compact index + source + AGENTS + facts + template). Highest value; also `maybe_generate_curiosity_requests`.
- `optimize-claude-md.py` — `optimize()` after `render("optimize_claude_md", ...)`.
- `suggestions/producer.py` — after its `render(...)` call.

Each needs a char budget lifted into `wiki_config.py` + `config.example.yaml` per the lift-hardcoded-to-CONFIG rule.

## Design question

One shared `limits.llm_max_prompt_chars` vs per-script limits. Per-script is more precise (compile embeds a source file, query embeds only the index, so their safe ceilings differ) but four near-identical knobs is config noise. Lean default: one shared limit sized to the standard 200K-token window, since all four target the same model. `query_max_prompt_chars` already exists — either generalise it or keep it query-specific and add one shared knob for the rest. Decide at implementation time.

## Done when

All four LLM-prompt call sites guard prompt size pre-flight; an oversized prompt aborts with `PromptTooLargeError` and a clear operator message (size + limit + per-component breakdown) instead of an opaque exit-1 SDK death.
