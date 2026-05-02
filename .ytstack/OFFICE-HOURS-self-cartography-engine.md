---
name: llm-wiki
one-liner: A self-cartography engine for solo knowledge workers — ingests daily logs, AI-agent memories, clippings, and other source streams into an always-current LLM-compiled wiki that the operator and their AI agents read from daily, with a depersonalized scale-out path to team and company knowledge.
mode: builder
stage: brownfield-retro
date: 2026-05-02
---

# llm-wiki — Office Hours pitch

**Mode:** Builder. **Stage:** Brownfield-retro — the project exists, has been iterating for several weeks, and this artifact retro-fits a ytstack-shaped pitch so `init-project` has a starting point.

## Why this exists (the deeper layer)

Surface framing: "personal-knowledge OS." Deeper framing: **self-cartography you actually use**. A solo knowledge worker's thinking is scattered across substrates — daily logs (behavior), AI-agent memories (working thought), clippings (curiosity), and assorted other streams. Each substrate is partial, none is queryable as a whole, and most are illegible even to the person who produced them.

llm-wiki turns those substrates into a single, always-current, machine-readable map with context and cross-references. The point is not preservation but **active use**: the operator reads articles as a daily reference; their AI agents pull from `knowledge/` instead of scanning raw memory; downstream skills cite specific articles; new substrates flow in continuously and the map gets refined by being used. **The wiki is not an archive; it is a working surface.**

This reframes several decisions: ingestion-path planning matters because it forces an inventory of where parts of one's thinking currently live; compile quality matters because the operator re-reads themselves and their agents consume the result; the depersonalized scale-out is downstream, not the goal.

## Direction

Two-tier split: engine lives in `<vault>/.wiki/`, vault is the user's actual Obsidian knowledge base. Pipeline: raw materials (`raw/`, `daily/`, AI-agent memories, clippings, planned external collectors) → LLM-driven compilation → structured articles in `knowledge/`. Always-current, queryable, AI-consumable, and actively read by operator + agents.

## Use moments (Q3 — desperate specificity)

All four overlap; none stands alone. Wedge-narrowing is explicitly rejected for this project:

1. **Cross-project memory loss** — insights from Project A invisible in Project B; agents in different projects see different memory.
2. **Memory bloat / signal loss** — `claude-memory` grows, MEMORY.md becomes unreadable, old entries decay.
3. **Daily-log archeology** — 10-minute searches through `daily/` + `raw/` for "when did I decide / learn X."
4. **Knowledge transfer to future-self** — in 6 months you forget why X is built that way.

Plus envisioned scale-out: depersonalized compilation as a pattern → personal-wiki → team-wiki → company-wiki.

## Usage signal (Q5 — observation)

Honest: not enough usage yet. The project is heavy on active-build, light on active-use. No "this surprised me" findings yet — that itself is the most useful signal. Don't over-architect for usage that hasn't been earned. The build-vs-use ratio is the project's #1 weak spot.

## Future-fit (Q6 — 3-year thesis)

Four overlapping theses make the project more essential, not less, as LLMs improve:

1. **Sovereignty** — as cloud LLMs absorb immaterial knowledge, the only personal-sovereignty layer is your own vault with your own compiler.
2. **Curated context for agents** — better LLMs still need curated context, not raw-memory dumps. The wiki sits between `raw/` and agent-prompt; it scales *with* model improvements rather than competing with them.
3. **Scale-out path** — the same compilation pattern (depersonalized) goes personal → team → company.
4. **Self-cartography that gets used** — see "Why this exists" above. Building llm-wiki forces an inventory and externalization of the parts of one's thinking that currently live in scattered substrates, *and* the compiled output is read daily by both the operator and their AI agents. The compounding loop matters: substrates feed the map, the map feeds reading and prompts, that reading surfaces gaps which feed back into substrates. When stronger models arrive, AI can act as a partner in self-knowledge instead of an interrogator with no context — but the map is already useful before that, every day, in current models.

Of the four, #4 is the most defensible — it pays off even if the wiki output stays modest, even if the scale-out never happens, even if cloud LLMs solve memory natively. The act of mapping plus the daily use of the map is the value.

## Risks / weak spots

- "All four use moments + scale-out vision" is platform-territory; classical office-hours discipline would push for a single-wedge focus. Builder-mode tolerates this because the operator is also the user — no external customer is waiting for a wedge.
- Build-vs-use ratio is heavy on build (Q5).
- Engine-vs-vault two-tier split is opinionated; cost is migration friction for any pre-existing vault.
- LLM-compilation cost (token + time) per ingest run grows linearly with raw-material volume; not yet bounded.
- **Multi-vault problem.** A user's notes commonly live across multiple Obsidian vaults; if llm-wiki only ingests one, the others are blind spots — and the project's own raison d'être (use-moment #1, cross-vault knowledge loss) reappears in its own setup. Open question for the roadmap: multi-vault ingest, or vault-merge-then-ingest?
- **Source-onboarding cadence.** Open milestone-scope decision: onboard older substrates (older notes, exports, dormant vaults, files from past systems) manually now, or wait until collectors + ingestion tooling automate the long tail? Risk of waiting: the map stays incomplete and the daily-use loop misses context. Risk of rushing: ingest-quality drops and the map gets noisy.

## What this project is *not*

- Not a wiki framework (no theming, no plugin API, no public-publish flow).
- Not a memory backend for AI agents (claude-memory + ytstack already cover that; llm-wiki *consumes* their output).
- Not a multi-tenant product. Solo by default; scale-out is depersonalization-by-config, not multi-tenancy.

## Recommended next step

`ytstack:init-project` to scaffold `.ytstack/` with `PROJECT.md` pre-populated from this artifact.

The existing `docs/design-decisions.md`, `docs/concept.md`, `docs/PROCESS.md`, `docs/plans/`, and claude-memory `project_*.md` artifacts need a **detect-analyze-migrate** pass — exactly the brownfield-without-`.ytstack/` workflow filed upstream as ytstack PR #15 (M010 scope clarification 2026-05-02). Until `ytstack:adopt-brownfield` ships, the migration is manual:

- `docs/design-decisions.md` → `.ytstack/DECISIONS.md` (move + update CLAUDE.md/README pointers)
- `docs/concept.md` + `README.md` → distill into `.ytstack/PROJECT.md` (keep `concept.md` as long-form public doc)
- `docs/PROCESS.md` → reference from `.ytstack/RUNTIME.md` (PROCESS stays public-engine-doc)
- `docs/plans/*` → `.ytstack/backlog/*` (agent-facing future-milestone pitches)
- claude-memory `project_*.md` → condensed into `.ytstack/KNOWLEDGE.md`
- claude-memory `feedback_*.md` → condensed into `.ytstack/PREFERENCES.md`
- `project_followups.md` → `.ytstack/M001-ROADMAP.md` (first milestone "Engine Bootstrap Polish")

`ytstack:plan-ceo-review` (concept mode) is **skipped** for this iteration — for a solo, long-term, iterative personal-infra project with thin usage signal, the marginal value of a stress-test is low. Reality is the better critic; ship M001, see what surfaces.
