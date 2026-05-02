---
name: llm-wiki-change
version: 1.1.0
description: |
  Standard change process for the LLM Wiki engine. Every feature change follows
  5 phases: Concept → Verify → Implement → Document → Visualize.
  Use for any new feature, pipeline change, or script modification.
  Trigger: "llm-wiki change", "wiki change", "engine change", "neues feature", "pipeline ändern"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

# LLM Wiki — Standard Change Process

Every change to the engine (`scripts/`, `hooks/`, `lib/`, `prompts/`, configs)
follows these 5 phases in order. Do NOT skip phases. Do NOT implement before
the concept is verified.

## Phase 1: Concept

Write the concept as a section in the relevant document (AGENTS.md,
docs/concept.md, or a new doc in `.ytstack/backlog/`).

The concept must describe:
- **What** changes (which scripts, flows, data)
- **Why** (what problem does it solve)
- **How** it integrates with existing flows (which scripts are affected)
- **Edge cases** and failure modes

Present the concept to the user for review.

## Phase 2: Verify Integration

Before writing any code, verify the concept against the existing system:

1. Read all affected scripts and identify exact code locations
2. Check that the concept doesn't break existing flows
3. Verify naming conventions match (file paths, frontmatter fields, etc.)
4. Check for gaps: does the concept cover all code paths?
5. Present the verification to the user: "Here's what I'll change in which files"

Get explicit user approval before proceeding.

## Phase 3: Implement

Write the code. For each file changed:
- Read the file first
- Make targeted edits (don't rewrite entire files)
- Test if possible (--dry-run, quick validation)

## Phase 4: Document

Update ALL affected documentation:

1. **docs/PROCESS.md** — Update the relevant process section (Mermaid + Prosa + Tables + Edge Cases)
2. **README.md** — Update usage examples if CLI interface changed
3. **AGENTS.md** — Update if the schema, repo layout, or operations changed
4. **.ytstack/KNOWLEDGE.md** — Add an entry under "Hard-won learnings" if the change embodies a hard-won lesson

Run the `sync-process-docs` skill to verify PROCESS.md matches implementation.

## Phase 5: Visualize

Update the Excalidraw architecture diagram:
- `docs/architecture.excalidraw`
- Only the affected sections need updating
- Use the `excalidraw-diagram` skill to render the PNG and verify (3-pass loop)

## Checklist

Before declaring done:
- [ ] Concept written and reviewed
- [ ] Integration verified, no gaps
- [ ] Code implemented and tested
- [ ] docs/PROCESS.md updated (Mermaid + Prosa)
- [ ] README.md updated (if CLI changed)
- [ ] AGENTS.md updated (if schema/layout changed)
- [ ] .ytstack/KNOWLEDGE.md "Hard-won learnings" entry added (if hard-won lesson)
- [ ] docs/architecture.excalidraw updated and rendered
