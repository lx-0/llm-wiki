---
name: sync-process-docs
version: 1.1.0
description: |
  Sync docs/PROCESS.md with the actual implementation. Reads all scripts, hooks,
  prompts, and config files, then updates docs/PROCESS.md to reflect reality.
  Use when scripts have changed, new features were added, or to verify
  documentation accuracy.
  Trigger: "sync process docs", "update process", "process docs aktualisieren"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
---

# Sync Process Documentation

## What This Does

Reads the actual implementation (scripts, hooks, prompts, config) and updates
`docs/PROCESS.md` to match. Ensures documentation never drifts from code.

Run this skill from the engine repo root (the directory that contains
`scripts/`, `hooks/`, and `docs/PROCESS.md`).

## Steps

### Step 1: Inventory all scripts

```bash
ls scripts/*.py hooks/*.py
```

For each script, extract:
- Argparse arguments (flags, defaults)
- Key constants (thresholds, timeouts, models)
- Import dependencies (especially shared modules: `ollama_client`, `flush_pipeline`, `_transcript`)
- Main flow (what it does, in what order)

Pay special attention to the single-source modules — they own cross-cutting
concerns and must be referenced correctly in the docs:

- `scripts/ollama_client.py` — every Ollama call (chat / chat_schema / chat_vision)
- `scripts/flush_pipeline.py` — staged-flush state machine
- `hooks/_transcript.py` — shared transcript walker for both hooks

### Step 2: Read current docs/PROCESS.md

Read the full `docs/PROCESS.md` and identify each documented process section.

### Step 3: Diff documentation vs implementation

For each process in `docs/PROCESS.md`, verify:
- Scripts mentioned exist
- CLI flags match argparse definitions
- Constants match (MIN_TURNS, MAX_RETRIES, COMPILE_AFTER_HOUR, etc.)
- Flow description matches actual code logic
- Edge cases listed are actually handled in code
- Routing tables match actual if/elif chains
- LLM configs match (model, allowed_tools, max_turns, permission_mode)
- Piggyback list matches `flush.py:_PIGGYBACK_COMMANDS` (currently 8 tasks)

Also check:
- Scripts that exist but are NOT documented in `docs/PROCESS.md`
- Features in code that aren't mentioned
- Deprecated code paths still documented
- Personal data leaking into the doc — anything personal (emails, customer
  names, hostnames, mbox paths) belongs in `CONFIG.personal`, not in the
  doc as a hardcoded example. Replace with `<placeholder>` patterns.

### Step 4: Update docs/PROCESS.md

For each discrepancy found:
- Update the documentation to match the code (not the other way around)
- Keep the format: YAML frontmatter + Mermaid diagrams + Prosa + Tables + Edge Cases
- Update the `updated:` date in frontmatter
- Bump the `version:` (semver) if the change is substantive
- If a new script was added, add a new section following the existing pattern

### Step 5: Report

Output a summary of changes made:
- Sections updated
- New sections added
- Discrepancies found and fixed
- Scripts not yet documented (flagged for future)
- PII removed (if any was found)

## Rules

- **Code is truth.** If `docs/PROCESS.md` says X but the code does Y, update the docs to say Y.
- **Don't change code.** This skill only updates documentation.
- **Preserve format.** Keep Mermaid diagrams, tables, prosa, edge cases structure.
- **Be specific.** Don't say "updated constants" — say "changed MAX_RETRIES from 3 to 5".
- **No personal data in the doc.** If you find an email, customer name, or hostname,
  replace with a `<placeholder>` and trust `CONFIG.personal.*` to fill it at runtime.
