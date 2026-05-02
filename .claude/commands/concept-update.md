---
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
description: Sweep recent changes and update the LLM-Wiki repo's concept docs, architecture diagram, AGENTS.md, and memory.
---

Review this conversation for non-trivial changes to the LLM-Wiki engine — new features, modified pipelines, new scripts, new piggyback tasks, architecture changes, prompt edits, config schema updates.

Then update ALL of the following — read each file first, make targeted edits, skip files that don't need changes. Don't rewrite — surgical edits only.

## 1. Concept document

`docs/concept.md`
- Move features from "planned" → "done" status as appropriate
- Add new features, pipelines, or data sources
- Update any concrete stats if mentioned (article count, collectors, etc.)
- Keep public-friendly tone (no personal vault paths, no customer/email specifics)

## 2. Architecture diagram

`docs/architecture.excalidraw`
- Use the `excalidraw-diagram` skill (in `skills/excalidraw-diagram/`) for editing — follow the mandatory 3-pass render-verify-adapt loop
- Add/update boxes, arrows, labels for new components
- Update piggyback pills if new tasks were added
- Verify all connections are correct
- Re-export `docs/architecture.png` after changes

## 3. Repo documentation

- `README.md` — add new scripts, commands, or usage examples
- `AGENTS.md` — update operations, scanner table, file tree, conventions
- `CLAUDE.md` — only if pointer changes (it's a thin pointer to AGENTS.md)
- `.ytstack/KNOWLEDGE.md` — add an entry under "Hard-won learnings" for any non-obvious gotcha discovered this session
- `.ytstack/backlog/<relevant>.md` — update if a backlog item moved status (seed → ready → implemented; promoted to a milestone moves it out of backlog/)

## 4. Config schema (if config changed)

- `scripts/wiki_config.py` — extend the matching dataclass + default
- `config.example.yaml` — document the new key with a comment
- Verify existing scripts use `CONFIG.<section>.<field>` instead of hardcoded constants

## 5. Memory (if working in a session-aware agent)

If the agent has session memory (Claude Code project memory or equivalent), update the project memory file with a short summary of what changed. Don't include private user data — repo-relevant facts only.

## 6. Verify

After edits:
- `bash -n wiki && bash -n lib/*.sh` — syntax check
- `gitleaks detect --no-banner` — no leaks
- One smoke test that exercises the changed surface (e.g. `wiki config get <new_key>` if a config field was added)

Commit with a single message that lists the touched surfaces in the body.
