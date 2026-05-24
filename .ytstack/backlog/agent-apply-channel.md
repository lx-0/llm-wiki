# Agent apply channel — fine-grained, structured, managed-section mutation for agents

Design pitch + reference-implementation analysis. Prior art: **OpenClaw wiki plugin**
(`docs.openclaw.ai/cli/wiki`, `github.com/openclaw/openclaw`, public). Companion to
`karpathy-comparison.md` (the conversational-edit half of Karpathy's pattern) and
`gbrain-comparison.md` (enrich-on-write trade-off).

**Purpose:** give an agent a *sanctioned, narrow* way to contribute structured
mutations to the wiki — without breaking the core rules (raw immutable; no freeform
hand-editing of compiled articles). Today an agent can only mutate `knowledge/` via
coarse engine commands; OpenClaw shows the fine-grained channel that's missing.

## The gap

Via `use-llm-wiki`, an agent's only knowledge-mutation paths are coarse:

- `wiki correct add` — but only **hard facts** (`knowledge/facts/`), a narrow genre.
- `wiki compile` / `wiki dream` — heavyweight, agent-triggered batch re-synthesis.
- `wiki produce` — re-run a Producer; not agent-authored content.

There is **no** "add this one structured claim / open question / contradiction /
confidence note to the right managed section" verb. An agent that learns something
small and structured during a session has nowhere cheap and safe to put it. It either
escalates to a `$$$` compile/dream, files a hard fact (wrong genre for most things),
or does nothing.

## Karpathy framing — this is the missing half

Karpathy's gist: *"the LLM makes edits based on our conversation, and I browse the
results in real time"* and *"you never (or rarely) write the wiki yourself — the LLM
writes and maintains all of it."* The wiki is continuously LLM-edited — **conversationally**.

llm-wiki today has the *autonomous-maintenance* half (compile = forward distill; dream
= scheduled cross-time re-synthesis) but **not** the *conversational/agentic fine-grained
edit* half. `wiki apply` is exactly that half. (Same gap Sid's capture-correction pitch
pokes at — see `OFFICE-HOURS-capture-correction-loop.md` and M025.)

## Prior art — OpenClaw `wiki apply`

OpenClaw's wiki plugin surface: `status · doctor · init · ingest · compile · lint ·
search · get · apply · bridge import · unsafe-local import · obsidian`.

The relevant verb:

> **`wiki apply`** — "Apply narrow mutations **without freeform page surgery**."
> Can: *"create/update a synthesis page, update page metadata, attach source ids,
> add questions, add contradictions, update confidence/status, write structured claims."*
> **Scope: managed generated sections only.**
> Rule: *"Use `wiki apply` instead of hand-editing managed generated sections."*

Plus richer retrieval than our grep-index + `wiki query`: `wiki search` modes
**find-person · route-question · source-evidence · raw-claim** (structured claims with
claim/evidence metadata). No permission/tiering model documented on OpenClaw's side.

(All extracted from OpenClaw docs, not run locally — verify against a live install
before copying semantics.)

## The deliberate line-cross

`wiki apply` softens **"the compiler is the *sole* author of `knowledge/`"** into
**"agents may apply *structured* mutations to *managed* sections."** This is a real
architectural choice, not free — same class of deliberate deviation as M005 (tasks
inside entity pages) and the memories reversal.

It is, however, **consistent with**:
- **Rule #1** (raw immutable) — apply never touches `raw/`.
- **Corrected Rule #2** — the *LLM* edits (not the human by hand), and only *structured*
  mutations into *managed* regions (not freeform body surgery). This is Karpathy-true.
- The **sentinel-region pattern llm-wiki already runs internally** (backlinks, calendar
  events, health-trends `## Trends`, takes blocks) + M005 two-layer `## State` sections +
  the facts subsystem. `apply` writes *only* into those, never freeform prose.

What it crosses: the strict "only `compile`/`dream` write knowledge/" stance. Decide
consciously.

## Proposed shape (llm-wiki)

A `wiki apply <op>` verb (+ `producers/`- or `facts/`-adjacent module) that maps each
structured mutation to an existing managed surface — never a freeform write:

| OpenClaw apply op | llm-wiki managed target |
|---|---|
| write structured claim | `knowledge/takes/` (M011 takes) or a new claims block |
| add open question | `raw/requests/` curiosity request (existing consumer) |
| add contradiction | lint contradiction surface / dashboard (propose-only) |
| update confidence/status | hard-fact status (`confirmed\|asserted\|provisional`) or page frontmatter |
| attach source ids | `compiled_from:` frontmatter |
| create/update synthesis page | gated — this is the line-cross; default OFF |

- Expose via `use-llm-wiki` **Contribute tier** (operator-gated, per the skill's existing
  tiering). The skill keeps `allowed-tools` = Bash/Read/Glob/Grep — `apply` is just
  another `wiki` subcommand, no direct file writes.
- Idempotent + sentinel-scoped, like every other managed-region writer.
- Consider porting the richer **search modes** (find-person → `knowledge/people/` +
  aliases; raw-claim → takes/claims) into the Read tier — cheaper agent grounding than
  `wiki query`.

## Open questions

- **Claim identity across recompile.** A structured claim needs a stable id that
  survives non-deterministic re-synthesis — the same identity problem as the X
  action-sync ledger (`x-action-layer.md`) and the killed `capture_index`. Solve once,
  reuse.
- **Does llm-wiki want a first-class "claim" object** (like OpenClaw's `claims.jsonl`),
  or are `takes` + `facts` enough? gbrain-comparison already weighed a claim/belief store.
- **Where do agent-applied mutations sit vs. the next compile** — does compile honor /
  preserve them (like manual `- [x]`), or overwrite? Must define, or apply-then-compile
  silently erases the agent's contribution.
- **Synthesis-page creation by an agent** is the sharpest line-cross — probably defer it;
  start with claims/questions/status into existing managed surfaces only.

## Relation to other work

- **X action layer** (`x-action-layer.md`) — both are agent/consumer-side mutation
  channels; share the identity-ledger problem and the operator-gate posture.
- **M025 capture-correction** — the operator-mobile analog of this agent-facing channel
  (correction without an agent in the loop).
- **`use-llm-wiki`** — the delivery surface (Contribute tier).

## Next step

Not validated. If pursued: `office-hours` on "what structured mutation does an agent
actually need to make, weekly?" before designing the verb — the OpenClaw surface is a
menu, not a requirement. Risk of over-building: a 6-op `apply` where 1 op (structured
claim) carries all the value.
