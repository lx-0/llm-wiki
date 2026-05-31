# Prompt-Aware Index Injection (UserPromptSubmit hook)

**Status:** backlog, optional / configurable feature. Evaluate **after** the SessionStart pointer-block refactor (shipped 2026-05-05) lands and we have observation data on whether the pointer alone is sufficient.

> Update 2026-05-30 (`3f1da92`): the pointer block was reworded from a bare path-list to a framed `<knowledge-base>` block (named tag + authority line + "consult BEFORE answering" trigger) precisely because the bare list wasn't being consulted reliably. The observation clock for "is push-at-session-start enough?" restarts on the new wording. The web survey behind that change also confirmed this item's premise: Karpathy-LLM-Wiki-v2 reports `index.md`-grep degrades past ~100-200 articles and the vault already holds 567 concepts — so deterministic per-prompt retrieval is the right next lever once the framed pointer has been observed.

**Origin:** 2026-05 conversation comparing this project's `session-start.py` injection pattern against Karpathy's pull-based index reading and Cole Medin's curated single-file `memory.md`. Conclusion: the SessionStart full-index-embed is an own-project extrapolation (cognitive-functions table in `docs/concept.md`, "Working memory" framing) that neither inspiration source actually does. The first refactor strips the body-embed and injects only a pointer-block. **This file** captures the optional next step: deterministic per-prompt retrieval as a hybrid of Karpathy's index-shape + Medin's query-time-retrieval (he does it for daily logs via SQLite — same shape, different substrate).

## Prior art — read before reinventing

The most evolved instance of this idea in the wild is **`yoloshii/ClawMem`**'s `context-surfacing` UserPromptSubmit hook. Before any implementation effort here, read their pipeline and code — many of the non-obvious phases (snooze filter, spreading activation, half-lives) are not things you'd think of from scratch.

ClawMem's per-prompt pipeline:

```
Hybrid search (BM25 + embeddings)
   → FTS supplement (full-text search backstop)
   → file-aware search (E13: prefer items linked to recently-touched files)
   → snooze filter (don't re-surface what was just dismissed)
   → spreading activation (E11: co-activation reinforcement — items frequently
                                  surfaced together get a relevance boost)
   → memory type diversification (E10: don't return 5 of the same type)
   → tiered injection (HOT / WARM / COLD)
   → wrap as <vault-context> + <vault-routing> blocks
```

Token budgets: 200 (balanced profile) / 250 (deep profile) per prompt — well under Anthropic's 10 000-char `additionalContext` cap. Multi-signal scoring uses keyword + semantic + graph traversal + co-activation + content-type-confidence + half-lives.

ClawMem also has a separate `postcompact-inject` SessionStart hook (1200-token budget, fires only after compaction) — captured separately in `postcompact-only-injection.md`. Their explicit position: *"context-surfacing on first prompt is more precise"* than unconditional SessionStart bootstrapping. That validates the direction of this backlog item.

For the lxw scope we don't need to reproduce all of ClawMem — we don't have embeddings or a graph layer, and we shouldn't add them just to power one hook. The minimum-viable variant is the deterministic ripgrep pipeline below. ClawMem stays as the reference for what the pipeline phases *could* become if observed need warrants it.

## Idea (minimum-viable, deterministic)

`UserPromptSubmit` hook runs before each user prompt is forwarded to the model. The hook:

1. Tokenizes the user's prompt, drops German + English stopwords.
2. If the remaining content-token count is below threshold (e.g. <3), exits silently — no injection.
3. Runs `ripgrep` over `knowledge/index.md` matching content tokens.
4. Scores each row by token-hits (require ≥2 distinct content tokens to match in one row, not just one).
5. Picks the top-1 (or top-2) row(s) above a min score.
6. Injects the matched row(s) verbatim — already shaped as `[[link]] | summary | sources | date` — wrapped in a clearly-labelled block:

   ```
   ## Auto-suggested wiki entries (from index.md grep, may be irrelevant — verify before relying on)
   - [[concepts/X]] — <one-line summary>
   ```

## Why it could work

- **Synthesis of both inspiration sources.** Karpathy's index-as-catalog + Medin's query-time keyword retrieval (he does this for daily logs already).
- **Saves the agent's first grep call** when the wiki actually contains relevant material.
- **Surfaces concepts the agent would not know to grep for.** The agent doesn't know what it doesn't know; the index does.
- **Cheap.** Ripgrep over a 297 KB file is sub-50 ms, well under perception threshold.
- **Deterministic.** No LLM call, no variance, no rate-limit exposure.

## Why it might fail / risks

1. **Anchoring bias.** A wrong top-hit primes the agent in the wrong direction. Worse than no hit, because the agent treats the injected pointer as a curated suggestion. Mitigation: clear "may be irrelevant" labelling; min-score threshold; top-1 only.
2. **Short / generic prompts** ("ok", "commit", "weiter", "yes") match either nothing or noise. Mitigation: skip-threshold on content-token count.
3. **Index distribution mismatch.** Current ratio is 567 concepts : 1 fact : 9 people : 36 projects. Almost any grep will return a concept page, regardless of whether the prompt is about a person/project/fact. Cannot be fixed at the hook layer — needs upstream work on the compile-output type distribution before this hook is meaningfully useful.
4. **Bilingual stopwords.** Single-language stopword list will leak common German particles into English prompts (and vice versa). Need a merged list, or language detection per prompt.
5. **Over-injection on long prompts.** A 500-token prompt about an unrelated topic will still find some weakly-matching row. Mitigation: require min-score, not just min-tokens.
6. **Privacy / scope creep.** Once we route every prompt through a hook, future "improvements" tend to creep (semantic re-ranking, LLM rerank, embedding lookup). Stay deterministic.

## Hard preconditions before implementing

- [ ] SessionStart pointer-block refactor landed and observed for ≥2 weeks (does the agent grep the index well enough on its own without this hook?).
- [ ] Compile-output type distribution is no longer concept-monoculture, OR per-MOC-aware retrieval is implemented (otherwise the hook can only ever return concepts).
- [ ] Stopword lists for `de` + `en` checked in (small, file under `lib/` or similar).
- [ ] ClawMem's `context-surfacing` pipeline read end-to-end (pipeline phases above) — even if we only ship the ripgrep variant, knowing what we're choosing not to build is part of the decision.

## Configuration shape (sketch)

In `config.yaml` (vault override) and `config.example.yaml`:

```yaml
hooks:
  prompt_aware_injection:
    enabled: false              # default OFF — opt-in
    min_content_tokens: 3       # skip if user prompt has fewer
    min_score: 2                # required distinct token hits per row
    top_n: 1                    # max rows to inject
    label: "Auto-suggested wiki entries (verify)"
```

## Open questions for evaluation

- Does the agent already grep the index reliably after the SessionStart refactor? If yes, this hook is redundant.
- Does the user perceive the auto-injected pointer as helpful or as noise / clutter / anchor?
- What is the false-positive rate (injected row is irrelevant) on a representative prompt sample?
- Should the hook also write to a log so we can audit hit/miss patterns post-hoc?

## Non-goals

- Semantic / vector / embedding retrieval. Stay deterministic — that is the entire point. If we want semantic retrieval, that's a different feature with different tradeoffs (and at that point the right thing to do is adopt or fork ClawMem, not rebuild).
- LLM-based rerank. Same reasoning.
- Multi-substrate retrieval (daily logs, raw/notes, etc.). Index-only for v1; broader retrieval is a separate evaluation.
- Full ClawMem-style pipeline (snooze filter, spreading activation, half-lives). These are valuable but require state we don't currently have (per-item dismissal records, co-activation co-occurrence matrix, content-type metadata). Each of those is its own feature; pulling them in here turns this hook into a project.
