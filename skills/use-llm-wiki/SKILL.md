---
name: use-llm-wiki
version: 1.0.0
description: |
  Discover and use a locally-available LLM-wiki through its `wiki` CLI — from
  any project, not just inside the vault. Read the knowledge base to ground
  answers in the operator's own compiled knowledge; contribute back (capture
  context, record a hard fact, ingest a source); or run maintenance (compile,
  lint, review). Step 1 locates the wiki (env var, walk-up, or registry) — if
  none is found, the skill does not apply and exits cleanly.
  Use when: an agent in any project should consult or feed the operator's
  knowledge base — "check the wiki", "what does my wiki say about X", "add
  this to the wiki", "ingest this into the wiki", "compile the wiki".
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - AskUserQuestion
---

# Use LLM-Wiki — query and feed a local knowledge base from any project

## Overview

An LLM-wiki is a Karpathy-pattern personal knowledge base: scattered personal
substrate (notes, agent memories, clippings, screenshots, meetings) compiled
into a queryable Obsidian vault of Markdown wikilinks. Its whole point is the
**inversion** — the wiki is read more often than it is written, by the operator
*and* by every agent given access.

This skill is the bridge from *any* project into that wiki. It lets an agent:

- **Read** — ground an answer in the operator's own compiled knowledge instead
  of guessing.
- **Contribute** — feed something back: capture this session, record a hard
  fact, ingest a source the agent just found.
- **Maintain** — run the pipeline: compile, lint, review.

It works from any working directory. The first thing it does is find out
whether a wiki is locally available at all — if not, it does nothing.

## Step 1 — Locate the wiki (the availability gate)

Probe these sources **in order**. Stop at the first hit.

1. **`LLM_WIKI_ROOT` env var** — explicit operator override, wins over
   everything. The vault root; the CLI is `$LLM_WIKI_ROOT/.wiki/wiki`.
   ```sh
   [ -n "$LLM_WIKI_ROOT" ] && [ -x "$LLM_WIKI_ROOT/.wiki/wiki" ] && echo "$LLM_WIKI_ROOT"
   ```

2. **Walk up from the current directory** for a `.wiki/wiki` executable — the
   agent is literally inside a vault (or a subdir of one). Confirm it's a real
   vault, not a lookalike, by checking for a `knowledge/` directory next to
   `.wiki/`.
   ```sh
   d="$PWD"
   while [ "$d" != "/" ]; do
     [ -x "$d/.wiki/wiki" ] && [ -d "$d/knowledge" ] && { echo "$d"; break; }
     d="$(dirname "$d")"
   done
   ```

3. **Registry** — `${XDG_CONFIG_HOME:-$HOME/.config}/llm-wiki/vaults`, a
   newline-delimited file of vault roots written by `wiki skills install
   --global`. Read it, skip entries whose `.wiki/wiki` no longer exists:
   - exactly one live entry → use it.
   - more than one → `AskUserQuestion` to let the operator pick (or honour
     `LLM_WIKI_ROOT` if it happens to be set).

4. **Nothing found** → the skill **does not apply**. Print one line — `no local
   LLM-wiki found — skill does not apply` — and stop. This is not an error, not
   a retry, not a reason to scaffold anything.

Once located, bind the CLI once and invoke it from anywhere — the `wiki` script
self-locates, so the agent's cwd is irrelevant:

```sh
WIKI="<vault-root>/.wiki/wiki"
"$WIKI" status     # sanity-check: prints config + hook state
```

## Step 2 — Pick the operation tier

Three tiers, escalating in cost and risk. Default to **Read**. Never silently
cross a tier boundary.

| Tier | What | Gate |
|---|---|---|
| **Read** | grep `knowledge/index.md` → `Read` the article; `wiki query` for synthesis | None — but prefer the index-grep path |
| **Contribute** | `wiki flush`, `wiki correct add`, `wiki ingest-html`, `wiki ingest-youtube`, `wiki collect <name>` | Confirm with the operator first — these write to the vault |
| **Maintain** | `wiki compile`, `wiki lint`, `wiki review-wiki`, `wiki curiosity`, `wiki suggestions`, `wiki process-inbox`, `wiki correct apply` | Explicit confirmation **and** name the cost |

## Read tier

The wiki's design is *compile once, query fast* — every compiled article is a
plain Markdown read, no embedding step, no retrieval. So for a lookup, **read
directly**:

```sh
grep -i "<topic>" "<vault-root>/knowledge/index.md"   # flat catalog: link · summary · sources · date
```

Then `Read` the matched article file(s). The index is large — always grep it
by topic, never load it whole.

Reserve **`wiki query`** for questions that need *synthesis across articles* —
it spends one LLM call (the configured compile model):

```sh
"$WIKI" query "How did the fleetd wire-protocol decision evolve?"
```

If the index-grep already answers it, don't run `wiki query`.

## Contribute tier

Mutating. Confirm with the operator before each, and report what landed.

- **`wiki flush`** — capture the current Claude Code context into `daily/`.
  Use when this session produced something worth keeping in the wiki.
- **`wiki correct add "TITLE" "TRUTH" [--status S] [--term T ...]`** — record a
  hard fact that overrides any raw source at compile + query time. Use when the
  agent learns the operator's sources contradict reality.
- **`wiki ingest-html PATH-OR-URL [--mode content|visual|both]`** — pull an
  HTML page (a doc, an article the agent just found) into `raw/articles/`.
- **`wiki ingest-youtube --url URL [--tier 0|1|2]`** — ingest a video /
  playlist into `raw/notes/youtube/`.
- **`wiki collect <name>`** — run one registered substrate collector
  (`wiki collect --list` to enumerate).

**Never write to `raw/`, `daily/`, or `knowledge/` directly.** The CLI
subcommands are the only sanctioned write path; `raw/` is LLM-read-only and
`knowledge/` is compiler-owned.

## Maintain tier

Heavy and/or costs real money. Confirm explicitly **and** state the cost.

- **`wiki compile`** — distill all changed `raw/` + `daily/` sources into
  `knowledge/` articles. Spends real Claude budget (the compile model);
  rate-limit-capped per run. Never run silently.
- **`wiki correct apply SLUG`** — agentically propagate a hard fact across the
  whole vault (strikes contaminated claims, fixes wikilinks, renames files).
  Agentic and `$$$` — the heaviest single command.
- **`wiki lint`** — structural + LLM contradiction checks. `wiki lint
  --structural-only` is the cheap, no-LLM variant.
- **`wiki review-wiki`** — per-article quality-score sweep (local LLM, free but
  slow).
- **`wiki curiosity`**, **`wiki suggestions`**, **`wiki process-inbox`** — the
  consumer-side loops. Local-LLM, but still slow; confirm before running.

## Rules

- **Availability gate is mandatory.** Always run Step 1 first. No wiki found →
  skill does not apply. Don't fabricate a vault, don't `git init`, don't offer
  to create one.
- **Read-first.** Prefer `grep knowledge/index.md` → `Read article` over
  `wiki query`. Grep the index by topic — never load it whole.
- **Stay in the Read tier unless asked.** Contributing and maintaining are
  operator decisions. Surface what you *could* do; let the operator green-light
  the tier crossing.
- **Mutating ops → confirm.** No `flush` / `correct` / `ingest` / `collect`
  without operator sign-off.
- **`$$$` ops → name the cost.** `compile` and `correct apply` spend Claude
  budget. Say so before running; never run them as a side effect.
- **Never write the vault directly.** Only the `wiki` subcommands write. `raw/`
  is read-only, `knowledge/` is compiler-owned.
- **Live data, not memory.** Re-grep the index / re-run `wiki status`; never
  argue from a cached earlier result — the pipeline mutates state constantly.
- **Surface dependency errors verbatim.** If `wiki` isn't executable or `uv` is
  missing, show the real error — don't paper over it or guess around it.

## Example

```text
User (working in some unrelated project): "what does my wiki know about the fleetd wire protocol?"

1. Locate the wiki:
   - $LLM_WIKI_ROOT unset.
   - Walk-up from cwd: no .wiki/wiki — not inside a vault.
   - Registry ~/.config/llm-wiki/vaults: one live entry → /Users/alex/.../lxw
   → WIKI=/Users/alex/.../lxw/.wiki/wiki

2. Read tier (no confirmation needed):
   grep -i "fleetd" /Users/alex/.../lxw/knowledge/index.md
   → concepts/fleetd-wire-protocol.md · "WebSocket + JSON-RPC 2.0 …"

   Read that article, answer from it. Cite the article path.

   Only if the question needed cross-article synthesis:
   "$WIKI" query "How did the fleetd wire-protocol decision evolve?"   (← one LLM call — mention it)

3. Offer the next tier, don't take it:
   "I answered from the compiled article. If you want this session's findings
    captured back into the wiki, I can run `wiki flush` — your call."
```
