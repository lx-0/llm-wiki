# wiki correct — deferred items

Phase 1 of `wiki correct` shipped: hard facts as a `knowledge/facts/<slug>.md`
substrate, injected into compile + query prompts at the highest authority,
plus structural lint via `negation_terms` grep, plus an agentic propagator
(`wiki correct apply <slug>`) that walks the vault and applies the correction.

These are the items deliberately *not* in Phase 1.

## LLM-paraphrase detection in lint

Today `check_facts_violations()` is a literal `lower().in(content_lower)`
substring grep over the `negation_terms` list. It misses paraphrases ("won
the Senkrechtstarter" vs "took home the Senkrechtstarter prize"). Cheap
($0) and explainable, but limited.

**Next step**: a second lint pass that asks the local Ollama model "does any
article contradict any fact in `knowledge/facts/`?" — same pattern as
`check_contradictions`, but framed as fact-violation rather than
cross-article contradiction. Still $0 because Ollama. Surfaces semantic
drift the grep misses.

## Severity levels for facts

All facts are equally authoritative right now. Could differentiate `priority:
hard | soft` — soft facts contribute prompt context but don't block compile,
hard facts trigger lint errors (not warnings) on violation.

Deferred until we have evidence the flat model is too coarse.

## Auto-trigger `correct apply` on `add`

Today `wiki correct add` only writes the fact file; the user must run
`wiki correct apply <slug>` separately. Could chain them with a `--apply`
flag (or prompt interactively), so a single command records the truth and
propagates it.

Deferred because (a) `apply` costs LLM tokens and the user should opt in,
and (b) when you add a long batch of facts in one session, you usually want
to review them all before kicking off propagation.

## File-rename safety net

`correct apply` is allowed to `git mv` knowledge files. There is no
post-condition check that the rename + every wikilink update happened
atomically. A failure mid-run can leave dangling links.

**Next step**: wrap the agent run in a transaction-style guard — snapshot the
vault tree before, diff after, revert on partial failure. Or: just trust
git's working tree and let lint surface broken_links afterwards. Probably
the latter is fine in practice; revisit if we see a real failure.

## Versioning + audit trail beyond git

Each fact tracks `created`, `updated`, `applied`. No history of *value
changes* (e.g. a fact was once "X is wrong" and is now "X is partly wrong").
Git tracks it; we have no in-app surfacing.

Deferred — git is enough until it isn't.

## Web / dashboard editor

Today: bash CLI plus `$EDITOR` for free-form edits. A future dashboard view
that lists all facts, their `applied:` status, recent violations, and lets
the user toggle / edit / re-apply would mirror the existing dashboard charts
(see `scripts/dashboard_stats.py`).

## Apply-against-raw policy

`correct apply` currently *reads* raw/ but only annotates daily/, never
mutates raw/. That is correct under the layered-substrates principle (raw
is immutable ground truth). But it means a contaminated raw source keeps
generating contaminated knowledge articles on every recompile. Mitigation
options for later:

1. Prepend a `corrections:` block to `index.md` listing applied facts so the
   compile prompt always sees them — already covered by the prompt-injection
   route, so this is redundant.
2. Add a "shadow correction" file alongside each contaminated raw source
   (e.g. `raw/notes/email/foo.correction.md`) that the compiler reads and
   honors. More structured but bigger surface area.

Defer until raw-source contamination is observed in practice (compile is
already prompt-aware of facts).
