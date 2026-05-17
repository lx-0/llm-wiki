---
name: backlinks-footer
one-liner: a compile-time `## Backlinks` footer in every knowledge/ article for AI agents reading the wiki, so backlink discovery becomes a `Read` instead of a structurally impossible search.
mode: startup
stage: pure-engineering-infra
parent-engine: llm-wiki
date: 2026-05-17
---

# Office Hours — Backlinks Footer

## Problem Statement

The use-llm-wiki skill (and any agent that consults the wiki from outside the vault) is restricted to a **Read tier**: `grep knowledge/index.md` → `Read` matched articles. This works for topic-based concept lookup. It **does not** work for graph-walk queries — discovering which articles link *to* a given concept. The wikilink graph in markdown is unidirectional; without an inverse index, backlink discovery requires a corpus-wide ripgrep that the skill's Read-tier explicitly forbids.

Agents reading the wiki today have **no first-class way to ask "what cites this concept?"** They either ignore the question (Skill-Compliant, blind), or violate the tier by ripgrepping `knowledge/` (skill-divergent, undocumented). Obsidian shows backlinks natively in its side-panel — but that's a human-only affordance. The compiled markdown the agent reads is silent about its inbound edges.

## Demand Evidence

Hard empirical run, 2026-05-17, against the lxw vault (1239 knowledge/ articles, 1464-line index.md). An Explore subagent under Read-tier-only constraints attempted three realistic agent queries:

| Query | Outcome | Files Read | Noise | Pain |
|---|---|---|---|---|
| Calendar/meeting concepts (topic) | Trivial — 5 signal hits, 0 noise | 5 | 0 | None |
| Backlinks to `jamie-ai` + `gmeet-collector` | **STRUCTURALLY IMPOSSIBLE** — concepts don't appear in index.md, no Read-tier path exists | 0 | — | Blocked |
| Voice/audio articles modified ≤14d | Solvable with manual `find -mtime` + `stat` + date math | 4 | 0 | Moderate |

The Read-tier currently has a hole exactly where the wiki's graph-nature is most useful. Of the three probes, **only backlinks failed structurally**. Topic-search and temporal-search are solvable with existing tools, however clumsily.

## Status Quo

What an agent does today when it needs backlinks:

- **Compliant path**: skip the question, answer from the article alone. Loses graph context.
- **Off-tier path**: `rg -l '\[\[<slug>\]\]\|<slug>\.md' knowledge/` against the corpus. Works but undocumented, escape-pattern-fragile, and bypasses the skill's stated discipline.
- **Operator workaround**: the human opens Obsidian and inspects the side-panel manually. Not available to autonomous agents (curiosity-loop, dream-cycle, spawn-milestone-team teammates).

## Target User & Narrowest Wedge

**Primary consumer**: any agent invoking the `use-llm-wiki` skill — that's Claude Code sessions in other projects, the curiosity-loop, the dream-cycle, future agent-team teammates. Multi-agent consumer base, all bound by the Read tier.

**Secondary consumer**: a human reading raw `knowledge/<article>.md` outside Obsidian (GitHub web-view, plaintext fallback, `wiki` CLI outputs piped to less).

**Narrowest wedge** (after premise-challenge round):

- **Only backlinks**. `search` and `recent` were considered but rejected — Query A worked trivially today, Query C had friction but was solvable. Pre-emptive tooling for non-existent pain is over-building.
- **Compile-time materialization**, not a query-time CLI wrapper. The agent already does `Read article.md` — the cheapest way to deliver backlinks is to make the article self-describing.

## Constraints

- **No vault-direct writes.** Must flow through compile-pipeline; sentinel-managed region pattern (already used in calendar collector) is the contract.
- **Idempotent.** A re-run produces byte-identical output. No append-on-each-compile drift.
- **Two-phase compile.** Per-source compile remains as-is; a new global post-pass walks the compiled `knowledge/` corpus, builds the `{slug → [incoming_slugs]}` map, and writes the `## Backlinks` footer into each article via sentinel.
- **Skill update mandatory.** `skills/use-llm-wiki/SKILL.md` Read-tier section must mention the footer; the question "how do I get backlinks?" must have a documented Read-tier answer.

## Premises

1. **The 1239-article vault has hit the backlinks-pain inflection.** Validated by today's probe: the failure was at this scale, not hypothetical.
2. **Agents are the primary consumer.** Validated by the inversion principle (wiki read more often than written, by agents). Codified in the use-llm-wiki skill.
3. **Frontmatter axes don't matter for THIS wedge.** Backlinks are derived from `[[wikilinks]]` in article bodies, not from frontmatter. We are not extending the axis-aware-search story here — that goes to backlog.
4. **Sentinel-managed regions are the right write-contract.** Pattern established (calendar collector); no new mechanism needed.
5. **`## Backlinks` at the article tail does not break the compile reader.** Verified: compile reads `raw/` + `daily/`, not `knowledge/`. The footer lives in the output of compile, not its input.

## Approaches Considered

### Approach A: `wiki backlinks <slug>` CLI subcommand (ripgrep wrapper, query-time)

~30 lines Python wrapping `rg`. Skill teaches the new command. No compile change.

- **Pro**: shippable in 1 hour; no compile-pipeline touching; zero new artifacts.
- **Con**: adds a tool the agent must remember; query-time ripgrep on every call; doesn't help humans reading raw markdown outside Obsidian; orthogonal to the engine's "compile once, query fast" doctrine.

### Approach B: Compile-time `## Backlinks` footer per article (CHOSEN)

Post-compile global pass writes a sentinel-managed `## Backlinks` block into every `knowledge/<article>.md` listing incoming wikilinks.

- **Pro**: zero new agent tool — the existing `Read article.md` flow returns backlinks; works for human readers outside Obsidian; reuses calendar-collector sentinel pattern; aligns with compile-once-query-fast.
- **Con**: requires two-phase compile (per-source → global sweep); every compile session writes a small diff into every article that gained an incoming link; ~O(corpus) extra read+write per compile run.

### Approach C: Sidecar `knowledge/.backlinks.json` (compile-time precomputed)

One JSON file, `{slug: [incoming]}`. Agent reads it directly or via a CLI helper.

- **Pro**: single artifact to update; queryable via `jq`.
- **Con**: new artifact in `knowledge/` that doesn't fit the Markdown-everywhere posture; agent must learn it exists; sync-drift smell.

### Approach D: Skill-doc-only (teach ripgrep pattern)

Update `use-llm-wiki/SKILL.md` to legalize `rg -l '\[\[<slug>\]\]\|<slug>\.md' knowledge/` as the Read-tier answer.

- **Pro**: zero engine code; pure Doug-Turnbull harness-discipline.
- **Con**: pattern is escape-fragile; agent must construct it correctly every time; doesn't help humans outside Obsidian; legalizes corpus-wide scans the tier was meant to forbid.

## Recommended Approach: Approach B

Compile-time materialization is the only path that:

- eliminates the "agent forgets the tool" failure mode (no tool to forget),
- benefits secondary consumers (humans reading raw markdown), and
- preserves the engine's compile-once-query-fast doctrine.

The two-phase compile cost is real but bounded (one corpus walk per compile run, idempotent via sentinel). The pattern this milestone establishes (post-compile global passes that materialize derived axes into article footers) is reusable for future axes — e.g. `## Related Concepts` or `## Compiled From` blocks could ride the same hook.

## Future-Fit

If the vault scales to 5k+ articles over the next 2-3 years (per `project_scaling_direction` memory, the 4-lever sequence: subtype-axis → MOC-first → lifecycle-tier → recursive-dream-cycle), the backlinks footer becomes *more* essential, not less — it's the only way agents can navigate the graph without doing O(corpus) ripgreps on every question. Recursive-dream-cycle in particular needs cheap backlink lookup to decide which articles to re-visit.

The footer mechanism does **not** preempt later work on axis-aware search (`wiki search --type --domain --author`). Those go to the deferred backlog (`.ytstack/backlog/search-tools.md`) and would build on a different mechanism (frontmatter-aware index/CLI), not on this milestone.

## Open Questions for Plan-CEO-Review

- Should the footer be plain markdown (`## Backlinks` + bullet list of wikilinks) or also include the matching `## Compiled From` block that today exists only in frontmatter? (Bundle-or-not.)
- Should the global sweep run on every `wiki compile`, or only when explicit `wiki compile --refresh-backlinks` is passed? (Always-on vs opt-in.)
- Does the sentinel-managed region survive `wiki correct apply` (the agentic vault-wide rename pass)? (Need to grep that script before scoping.)

## Backlog Cross-Refs

- `.ytstack/backlog/search-tools.md` (to be created) — axis-aware search (`wiki search --type --domain --author`) and temporal-axis (`wiki recent`); deferred per Q4 narrowest-wedge round, both rejected as pre-emptive tooling.
