# Concept — Voice source-ref (frontmatter) + Voice-intent producer → agent_task

Origin: operator looked at `daily/2026-06-12/voice.md`, two asks:
1. The source reference into `raw/` is a dead wikilink.
2. A producer (agentic) that detects when a voice note is *actionable* (a TODO/instruction
   to the wiki orchestrator) and routes it into execution.

Two independent changes. **A** is small + fully specified. **B** is a feature (milestone-sized).

---

## Change A — Voice source reference via frontmatter (kills the dead wikilink)

**Problem (verified).** `collectors/voice.py:_append_daily_rollup` (line 289) appends:
```
- **22:12** · <first-line> → [[voice-2026-06-12-2212-…-mit]]
```
The `[[…]]` targets `raw/voice/<stem>.md`. `.obsidian/app.json` has
`userIgnoreFilters: ["raw/"]` (intentional mobile-perf exclusion) → Obsidian never
indexes the target → the link renders unresolved/dead. Provenance is text-only, non-navigable.

**Operator decision.** Keep the source *referenced*; drop the wikilink; **put the reference
in frontmatter**; mobile-index cost must NOT rise (frontmatter is not a graph edge, raw/ stays excluded).

**What changes.**
- `collectors/voice.py:_append_daily_rollup`: body line loses the `→ [[…]]` suffix
  (becomes `- **HH:MM** · <first-line>`).
- The raw source path (e.g. `raw/voice/voice-2026-06-12-2212-…-mit.md`, vault-relative)
  is recorded in the `daily/<date>/voice.md` frontmatter as a growing `sources:` list.

**How it integrates.** `core/daily_capture.py` is the documented single chokepoint for all
`daily/<date>/<source>.md` writes, but today it is pure body-append (no frontmatter awareness).
- Add `append_with_source(date, source, line, source_ref)`: flock-protected read-modify-write
  that (1) ensures a `---\nsources:\n  - …\n---` frontmatter block, (2) appends `source_ref`
  to the list (dedup), (3) appends the body line. Pure `append()` stays for callers without
  a source ref.
- Belongs in `daily_capture` (shared) so meetings/pictures can adopt the same provenance later —
  not re-implemented per collector.

**Edge cases.**
- **Existing files have no frontmatter** (every current `daily/*/voice.md`). First
  `append_with_source` injects the block. Historical files: leave as-is OR one-shot backfill —
  **decision needed** (lean: leave historical, only new writes get it; the operator's complaint
  is about new capture).
- Append-only → read-modify-write, still flock-safe.
- **Unbounded list precedent**: `compile_health.md` warns an unbounded `compiled_from:` list once
  broke the Read-tool token limit. Voice volume is 1–5/day → non-issue, but the list is per-day
  (resets daily), so it never grows unbounded.
- Frontmatter key: use `sources:` (distinct from compile's `compiled_from:`, which is set on
  *compiled knowledge articles*, not source-substrate files).

---

## Change B — Intent producer → extensible intent-dispatch (first handler: `task`)

**Problem.** Some intake notes are de-facto instructions ("baue X", "lege Y an", "recherchiere Z").
Today they sit inert in `raw/`. The example ("Können wir … macht das Sinn?") is *borderline* —
an idea/question, not a clear TODO. Detection must be genuinely agentic (fuzzy classification),
which is why a producer (LLM) is justified and not a deterministic rule.

**Operator decisions.**
- #2: route detected actionable items into the **agent_task** framework — close the loop to execution.
- **Extensibility (new):** an intake intent is NOT only ever a "task". The classifier must be able
  to emit different *outcome kinds*, and the routing must be extensible — both across **outcome
  kinds** (task / fact / research / idea / question / …) and across **intake substrates** (voice
  first, later captures / email / screenshots feeding the same classifier).

**Architecture — intent-dispatch seam (mirrors the Collector/Producer registry idiom).**

1. **New producer `intents`** (`scripts/producers/intents.py`), registered in `producers/__init__.py`,
   runs in `compile_stages/post_passes.py`'s per-source loop. Gates:
   - `enabled_config_key="features.extract_intents"` (default **False** — off until validated).
   - `source_glob_config_key="limits.intent_source_globs"` → `["raw/voice/*"]` (extend the glob list
     to add new intake substrates — no code change).
   - Prompt (in `prompts/`, never inline) classifies the note into an **intent record**
     `{kind, summary, confidence, source}`. **Conservative**: default `kind: none`; the borderline
     "macht das Sinn?" example must classify as idea/none, NOT auto-executable task.
2. **IntentHandler registry** (`scripts/intents/` — new subpackage, same `@register` + Protocol
   shape as `producers/base.py`). Dispatch picks a handler by `intent.kind`. Each handler owns its
   outcome destination. Unknown/`none` kind → no-op (logged). This is the extension point: a new
   outcome kind = one new handler module, registered, done.
3. **First handler shipped: `task`** → writes a frontmatter-stamped record to `tasks/` (operator-facing,
   Obsidian-visible, `status: pending`), with `source:` provenance + `confidence` + `kind`. Idempotent:
   re-enqueue guard keyed by source-path/hash, bookkeeping in `state/` (NOT in `tasks/`).
4. **Static orchestrator spec** `prompts/agents/orchestrate-tasks.md` (one hand-authored agent_task
   spec, `allowed_tools` + `model` + dashboard `button`) reads `tasks/` `status: pending`, executes
   them, marks done. **Operator-gated** (button or scheduled review) — never auto-run inside compile.
   Output destination (M005 Action Items, a project note, a spawned sub-task) is the spec body's job.

**Future handlers (extension points, NOT built now):** `fact` → facts subsystem; `research` →
curiosity/web_research; `idea` → a backlog/idea note; `question` → qa/knowledge-gap; `event` →
calendar. Each is an additive handler module; the producer + registry + config stay unchanged.

**Why a registry, not an `if kind == …` ladder.** The codebase already standardizes on declarative
registries (Collector, Producer). The dispatch must be open for extension (new kinds) and closed
for modification — adding `fact` later must not touch the producer or the `task` handler.

**Why enqueue-then-gate, not auto-execute.** No silent auto-execution of (possibly destructive)
work from a fuzzy classifier. Producer = detection. Handler = routing. agent_task spec = reviewable execution.

**Why NOT one agent_task spec per note.** `agent_task` specs are STATIC templates with `${var}`
placeholders, enumerated by `list_specs()`. One file per note would pollute `prompts/agents/` and
break `list_specs` (every `.md` is parsed as a spec). Hence: ONE static orchestrator spec consuming
the `tasks/` queue, not N per-instance specs.

**Edge cases / risks.**
- **False positives** are the main risk — most notes aren't actionable. Confidence gate + conservative
  prompt (default `kind: none`).
- **Cost**: +1 LLM call per matched intake note in post-pass (gated, off by default).
- **Idempotence**: no re-classify/re-dispatch on recompile (source-hash guard in `state/`).
- **Provenance** ties back to Change A (`source:` = raw path).
- New config keys → `migrate_config_keys.py` entry in the same commit (hard rule).
- Template-resync: `templates/` + `config.example.yaml` in the same commit.

**Scope for this arc (operator: A+B as one ad-hoc arc).** Ship: producer `intents` + IntentHandler
registry + `task` handler + `tasks/` queue + orchestrator spec + config/migration/docs/diagram.
Future outcome-kind handlers are documented extension points, not built.

---

## Decisions resolved (operator, 2026-06-13)

1. **A — backfill: ALL.** One-shot migration parses existing `[[stem]]` links in `daily/*/voice.md`
   back into `sources:` frontmatter and strips them from the body.
2. **A — shared method.** `daily_capture.append_with_source(...)` (shared chokepoint).
3. **B — process.** A + B as ONE ad-hoc arc (no milestone ceremony).
4. **B — queue location.** Operator-facing records in new top-level `tasks/` (Obsidian-visible,
   `status:` lifecycle, dashboard-queryable). Idempotency bookkeeping in `state/`. Rationale:
   operator-gated execution requires the records be reviewable/editable — rules out hidden `state/`
   and Obsidian-excluded `raw/`. `tasks/` is a distinct fourth layer beside raw+daily (source),
   knowledge (compiled), and now actionable working items.
5. **B — extensibility.** Intent-dispatch handler registry, not task-only. `task` handler ships now;
   other outcome kinds (fact/research/idea/question/event) are additive handler modules. Intake
   substrates extend via the source-glob list.

---

## Vault information model — the `workspace/` layer (locked 2026-06-13)

The operator pushed past "where does the task queue go?" to the real question: **how do you
classify the *nature* of information in a knowledge base?** Two orthogonal axes, not topic.

### Axis 1 — cognitive nature (Tulving, adapted by every PKM system)

| Type | Essence | Vault layer |
|---|---|---|
| **Episodic** | events, time-indexed: "what happened when" | `daily/` |
| **Semantic** | timeless distilled concepts/facts | `knowledge/` |
| **Procedural** | "how to do X" | (within `knowledge/`) |
| **Intentional / operational** | open loops, intentions, commitments — carries a **state** | `workspace/` ← was missing |

`raw/`, `daily/`, `knowledge/` are all **descriptive** — they assert *what is / was / is known*.
A todo, an idea, a triage item is **operational**: it carries a lifecycle status
(`pending → done/dismissed`), not a claim about the world. That is the category the vault lacked a home for.

### Axis 2 — lifecycle & authority (the data-structures / CQRS reading)

| Layer | Data-structure analogue | Mutability | Owner |
|---|---|---|---|
| `raw/` | append-only event/source log (write-once) | immutable | collector |
| `daily/` | time-series / partitioned event log | append-only | collector/hook |
| `knowledge/` | materialized view / read-model (projection over sources; `compile` = the materialization job) | derived, regenerable | LLM |
| `workspace/` | operational/transactional store with a state-machine | **mutable, lifecycle** | **operator (+ their agent)** |

`raw/` + `daily/` are the write-model (fact stream); `knowledge/` is the denormalized read-projection;
`workspace/` is the **only layer with mutable lifecycle state**. The intent classifier is a **router**:
it takes a capture event and decides which structure it belongs to.

### `kind` taxonomy — the sharp consequence

The dividing line is **"does this carry an open loop / a state?"**, NOT the topic:

- **`task`** → operational, has a defined done-state → `workspace/` ✅
- **`idea`** → GTD "incubate / someday-maybe" — not yet actionable, *might* become a project; has a
  status (raw → maturing → promoted/dropped) → operational → `workspace/` ✅
- **`note`** → a pure **reference** note (factual, no open loop) is by definition **not** working
  state but **semantic** → belongs toward `knowledge/`, not the inbox.
- **`none`** → genuine noise only (mic-checks, "hallo hallo", test) → dropped.

Practically (GTD: don't sort at the door): the inbox captures *everything substantive* with
frontmatter `kind` + `status`; **triage** is where a `note`-reference promotes to `knowledge/`,
`task`/`idea` stay as operational loops in `workspace/` until done/dismissed. The classifier only
has to coarsely split loop-vs-reference-vs-noise.

### Structure

```
workspace/
  inbox/        ← detected intents awaiting triage (kind: task|idea|note, status: pending)
  todo.md       ← the operator's running next-actions list (general TODO)
```
The intent producer (voice + pictures) writes into `workspace/inbox/`. `tasks/` (shipped earlier
this arc) is renamed → `workspace/inbox/` (too narrow a name for idea/note too).

### Policy — `workspace/` hygiene + agent access (operator, 2026-06-13)

- **Kept clear, current, tidy.** `workspace/` is a working desk, not an archive. Stale/done/
  dismissed items get cleared; on user or agent request it may be **distilled** (summarised,
  promoted to `knowledge/`, pruned) to stay legible. An overgrown inbox defeats the GTD "trusted
  system" property.
- **The vault owner's agent may work *in* `workspace/`** — read AND write. This is the one
  content layer agents operate inside by design (unlike `raw/`/`daily/` = read-only source, and
  `knowledge/` = compile-owned). Agents triage, distil, append to `todo.md`, flip statuses.
- Intake substrates feed it identically: voice + **pictures** (photographed tasks/ideas/notes)
  run through the same intent pass → `workspace/inbox/` (extend `intent_source_globs`).

### Build delta vs what shipped earlier this arc

- Rename `tasks/` → `workspace/inbox/` (paths, handler, seed, dashboard, AGENTS.md).
- Broaden classifier prompt: `none` = noise only; question/"macht das Sinn?" → `idea`; add `note`.
- Add `idea` + `note` handlers (registry already supports it).
- Add `intent_classify_model` knob (default `claude-haiku-4-5` — classification ≠ reasoning,
  opus is overkill + 10× slower/costlier; mirrors `route.py`'s haiku tiers).
- Add pictures to `intent_source_globs`.
- Seed `workspace/` + a starter `todo.md` via templates so the layer always exists.
