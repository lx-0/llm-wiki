# Recursive session summary (Phase 2 of flush-context gen-2)

**Status:** deferred — re-evaluate after 4-6 weeks of operating with the
gen-2 per-class budgets (2026-05-16 fix).

## Trigger

Per-class budgets (50K assistant / 10K user / 10K tool) cover the *current*
shape of analytical sessions on lxw. Phase 2 only triggers if observation
shows long sessions still losing material that should reach `daily/<date>/
sessions.md`. Concretely:

- session-end staging files (`<vault>/.wiki/sessions/session-flush-*.md`)
  with `[... truncated ...]` markers at the head, or
- post-compile audits where the operator says "this finding was in the
  conversation but didn't reach `knowledge/`".

If neither happens, do not build Phase 2.

## What it would be

The asymmetric-truncation approach (Phase 1) drops the oldest turns when a
budget overflows. Phase 2 swaps "drop" for "summarise": older turns get
recursively compressed into a rolling summary, the recent tail stays
verbatim.

The lineage:

- **Recursive summary** — arxiv 2308.15022 (long-term dialogue memory).
  `Summary_n = f(Summary_{n-1}, new_chunk)`. Avoids the flat-loss of a
  single-pass summariser.
- **NexusSum** — ACL 2025. Multi-agent iterative refinement for long-form
  preservation. Higher fidelity than single-pass at the cost of multiple
  LLM calls.
- **TaciTree** — arxiv 2503.07018. Hierarchical tree with drill-down. The
  consumer (compile.py) decides how deep to descend per source.

For our shape — markdown vault, compile.py downstream — TaciTree is over-
engineered (we don't drill at consumption time). The Anthropic-compaction
pattern `pause_after_compaction: true` + custom instructions is the
closest practical reference. Recursive-summary is the lean variant of
the same idea.

## Sketch

- `hooks/_transcript.py` gains `_summarise_old_turns(turns, n_keep=20)`:
  partitions into `older` + `tail`, calls a fast model (Haiku) with a
  prompt designed to preserve narrative findings, emits one rolling
  `## Earlier summary` block prepended to the verbatim tail.
- Budgets stay: the summary itself counts against `assistant_text` budget.
- Trigger condition: total turns > N (start at 60), OR pre-truncation
  prose volume > 1.5× the assistant_text_budget.
- The summary call must NOT block hook exit; spawn in background like
  flush.py itself.

## Risks not yet de-risked

- Hooks have a 10s timeout. Sync summarisation of a 60-turn session is
  not feasible inside that window — has to be async via the same spawn
  pattern flush.py uses, and the summary lands as a separate artifact
  that the staging pipeline picks up. Re-architecting around that is
  the real work, not the summariser itself.
- The model picks substance non-deterministically. We'd need a test
  fixture: long synthetic transcript with known findings, verify the
  summary preserves them. Without a fixture this is hard to keep honest.
- Cost: an extra LLM call per long-session flush. Probably $0.01-0.03 on
  Haiku, but worth counting.

## What to read before starting

- `hooks/_transcript.py` — current Budget/Turn architecture
- `prompts/flush_extract.md` — extractor template (the consumer of the
  staged context)
- `scripts/flush.py` — the SDK-driven extraction call after staging
- `.ytstack/KNOWLEDGE.md` § "Flush context — Karpathy/Cole pattern" — the
  gen-1 + gen-2 history this builds on

Not a milestone yet. Promote to M### only when observation data justifies.
