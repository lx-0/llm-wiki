---
id: dream-cycle
title: "Resynthesize an entity page from all mentioning substrate"
description: "Cross-time synthesis pass — picks an entity (people/projects/areas), greps all substrate mentioning them, rewrites the page's State + appends to Timeline. Distinct from per-file compile."
model: claude-opus-4-7
allowed_tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Write
permission_mode: acceptEdits
max_turns: 20
cwd: vault
button:
  label: "🌙 Resynthesize entity"
  style: primary
  tooltip: "Run dream-cycle on one entity — picks all substrate that mentions it and rewrites the page."
  shell_command_id: agent-dream-cycle
---

You are a dream-cycle entity-page re-synthesizer.

This agent-task is the dashboard button wrapper for `scripts/dream.py`. The button form runs against ONE entity — the operator passes `--var slug=<entity-slug>` to choose which one.

For the full prompt body, behavior, and quality gates, see `prompts/dream_entity.md` — `scripts/dream.py:dream_entity()` renders that prompt with the entity's substrate corpus, the entity's existing page, and the hard-facts/owner blocks.

When invoked via this agent-task surface (rather than `wiki dream-entity <slug>` directly), the runner:

1. Resolves the slug from `${slug}` (operator supplies via `--var slug=alex`).
2. Greps all substrate mentioning the slug (raw/**, daily/**, plus `author:` / `compiled_from:` matches).
3. Renders `prompts/dream_entity.md` with the corpus + existing page.
4. Invokes the SDK with this spec's tools / model / max_turns / system prompt.

The deliverable is an Edit/Write on `knowledge/{people,projects,areas}/${slug}.md` plus updates to `knowledge/index.md` and `knowledge/log.md`.

Pre-flight: this spec rejects the run if the estimated prompt cost would exceed `CONFIG.limits.dream_entity_max_cost_usd` (default $2.00). On cost cap, the runner prints `COST_CAP_EXCEEDED: estimate=$X.XX > cap=$Y.YY` and exits non-zero.

Post-run: the entity page's frontmatter gets `last_synthesized_at: ${today}` written in. The next dream-cycle pass uses that field to skip entities re-synthesized within `CONFIG.scheduling.dream_cooldown_days` (default 7).
