# Dream Cycle — scheduled cross-time synthesis

A periodic (probably nightly) synthesis pass that reads recent `daily/` + `raw/transcripts/` + `raw/notes/` and produces synthesis-articles in `knowledge/`. Adopted from gbrain's "dream cycle" pattern. See `gbrain-comparison.md` for context.

## What it adds beyond compile

`compile.py` today is **per-file distillation** — one substrate-file → one or more `knowledge/` updates. It does not look *across time* or *across substrate-files* to find emergent patterns. The curiosity loop (`maybe_generate_curiosity_requests`) does spot gaps but has no consumer.

Dream-Cycle is **cross-time synthesis** — read the last N days of substrate-additions, find recurring threads, write new connection-articles or update existing ones with weekly/monthly summaries. Different output shape from compile.

Example outputs:

- `knowledge/connections/weekly-2026-w19.md` — "Three sessions touched agent-config staleness; two emails mentioned the same Yesterday-AI repo split; consider promoting to a project-page."
- `knowledge/projects/jamie-rollout.md` updated with "5 meetings this week, theme: [X]."
- `knowledge/takes/jane-doe.md` (if `takes-substrate.md` lands) gets new entries from cross-meeting belief patterns.

## Why per-file compile isn't enough

- A theme that appears in 5 separate Jamie meetings is invisible to each individual compile pass (each only sees its own file + `index.md`).
- Curiosity-loop gaps are spotted per-file but never reflected on in aggregate.
- Operator currently has to manually trigger "look at all my last week and summarize" — no engine surface for it.
- Per-substrate-volume is rising (Jamie + YouTube + email + screenshots ≈ 30-50 new substrate files / week in lxw). Manual review doesn't scale.

## The proposed shape

```bash
wiki dream                         # last 7 days, default
wiki dream --since 2026-04-01      # custom window
wiki dream --dry-run               # show what would be synthesized, write nothing
wiki dream --target weekly         # synthesis kind: weekly | monthly | adhoc
```

Or as scheduled piggyback in `flush.py`:

```yaml
piggybacks:
  dream_cycle:
    enabled: true
    cooldown_hours: 24
    window_days: 7
    target_dir: knowledge/connections/
```

Output: new or updated `knowledge/connections/synthesis-<period>.md` files. Plus side-effects on entity-pages (if `entity-pages-state-timeline.md` lands) and takes (if `takes-substrate.md` lands).

## Touchpoints

- `scripts/dream.py` (new) — main entry. Walks `daily/` + relevant `raw/` subtrees in the window, builds a single big context block, calls Claude Agent SDK with a synthesis prompt, writes outputs.
- `prompts/dream_main.md` (new) — synthesis prompt. Distinct from `compile_main.md`: looks across, not within. Output schema: list of synthesis-targets with operations (create/update/append).
- `prompts/dream_main_system.md` (new) — minimal system prompt, same convention as `compile_main_system.md`.
- `flush.py:_LEGACY_PIGGYBACK_COMMANDS` — register as auto-piggyback if cooldown reached.
- `wiki` CLI — add `wiki dream` subcommand, mirrors `wiki compile` shape.
- `prompts/agent_*.md` could host this instead as an agent-task (M004 framework). Cleaner — no new top-level CLI surface, drops into existing dashboard button infrastructure.

## Choice: piggyback / CLI / agent-task

| Surface | Pros | Cons |
|---|---|---|
| Standalone `wiki dream` + piggyback | Direct, debuggable, no agent-framework overhead | Adds another CLI surface |
| Agent-task (`prompts/agent_dream-cycle.md`) | Reuses M004 infrastructure (buttons, dashboard, runner) | Less direct; opaque debugging if synthesis fails mid-pass |

Recommend **agent-task** path — M004 framework is built for exactly this shape, plus we get the dashboard "Synthesize last week" button for free.

## Open questions

- **Window default.** 7 days, 14, 30? Probably 7 with `--since` override.
- **Output destination.** New `knowledge/connections/synthesis-<period>.md` files vs. update existing topic articles vs. fresh `knowledge/synthesis/` subfolder. Probably `connections/` because the pattern matches (cross-source connection-finding).
- **Cost cap.** Synthesis context can be large (a week of `daily/` + transcripts ≈ 50-200K tokens). Per-run budget guardrail similar to YouTube Tier-3-cloud's `--allow-cloud`. Probably hard cap on context-tokens with truncation strategy (most-recent-first, drop oldest until under cap).
- **Re-run idempotency.** If `wiki dream --since 2026-04-01` runs twice, does it produce two copies or update the existing one? Probably: each run produces a new dated file (`synthesis-2026-w19.md`); two runs in same week update the same file via marker-based region replace (M004 pattern).
- **Producer ↔ consumer cycle.** Dream-Cycle reads compiled `knowledge/` + raw substrate, writes back to `knowledge/`. Next compile pass sees the new synthesis articles and incorporates them. Could create amplification loops. Mitigation: synthesis articles get `type: synthesis` frontmatter; compile prompt explicitly excludes them from source citation (read-only).
- **Frequency in practice.** Daily is too noisy; monthly too coarse. Weekly cron at e.g. Sunday night is the natural fit.

## Interaction with the existing curiosity loop

The curiosity loop (`compile.py:maybe_generate_curiosity_requests` → `raw/requests/`) currently has no consumer. Dream-Cycle could **be that consumer** — when synthesizing the week, also process accumulated `raw/requests/*.json` and emit either: gap-filled articles, or `raw/notes/deep-<slug>.md` deep-scan requests.

Doing both at once couples them in a way that might be cleaner than each-alone. But it also doubles the failure-surface. Probably better to ship Dream-Cycle first standalone, then revisit curiosity-consumer-gap.md as a Dream-Cycle extension.

## Lift estimate

- Synthesis prompt + system prompt: 0.5 day (iterative)
- `prompts/agent_dream-cycle.md` agent-task spec: 0.5 day
- Piggyback wiring + cooldown: 0.5 day
- First dogfood pass on lxw vault (last week's substrate): 1 day, mostly LLM time + reviewing output quality
- Marker-based idempotency / re-run logic: 0.5 day
- Tests (small — agent-task + prompt rendering): 0.5 day

**~3.5 days end-to-end** as an agent-task. Standalone CLI surface would add ~1 day.

## Risks

1. **Output quality unpredictable.** Cross-time synthesis is harder than per-file distillation; LLM tends to write generic "this week was busy" filler. Mitigation: prompt aggressively rewards specificity ("name the three concrete patterns; cite which substrate-files"); reject runs that produce <N specific cross-references.
2. **Cost.** Weekly synthesis with full context could be $0.50-2 per run. Annual cost $25-100 for the lxw operator scale. Acceptable for the value if quality holds; pre-run cost-estimate gate before sending the request (analogous to YouTube cloud guardrails).
3. **Amplification feedback.** Synthesis articles re-read by next compile. Mitigation: `type: synthesis` excluded from compile-prompt source-citation.
4. **Stale state.** Synthesis from last week becomes stale when new substrate arrives. Mitigation: `last_synthesized_at` + dashboard surface showing when synthesis last ran; lint warns when synthesis articles are >14 days old.
5. **Operator overwhelm.** Weekly synthesis articles accumulate in `knowledge/connections/`; eventually 50+ files. Mitigation: archive after N weeks or fold older synthesis into monthly/quarterly summaries (recursive dream-cycle).

## Ripens when

- Substrate-rate exceeds ~10 new files/day for >2 weeks (lxw is probably already there).
- OR operator hits "I forgot what I worked on three weeks ago" and has to grep `daily/`.
- OR `entity-pages-state-timeline.md` lands and Timeline-entries need cross-time aggregation that compile alone doesn't provide.
- OR `takes-substrate.md` lands — Dream-Cycle is the natural cross-time producer for promoting recurring beliefs into takes.

## Status

Backlog. Sibling to `entity-pages-state-timeline.md` and `takes-substrate.md`. Highest standalone value of the three (works without the others); also strongest synergy when bundled. Best ordering for a bundled M005: Entity-Pages first (gives State+Timeline a place to land), Takes second (uses entity-pages as the "who"), Dream-Cycle third (synthesizes across both).

Standalone-first ordering: Dream-Cycle, because it produces immediate value (weekly summaries) without prerequisite schema changes.
