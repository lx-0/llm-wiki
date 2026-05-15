# Compile agent: stop letting the agent write to the filesystem

## Status

Open. Short-term mitigations shipped 2026-05-15 (see commit). Long-term refactor
deferred — significant change to compile flow.

## The bug

`scripts/compile.py` spawns the Claude Agent SDK with:

- `cwd=ROOT_DIR` (vault root, e.g. `~/Library/.../lxw/`)
- `allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"]`
- `permission_mode="acceptEdits"` (silent auto-accept)
- `setting_sources=[]` (no CLAUDE.md guardrails reach the agent)

The substrate the agent compiles (`daily/*.md`, `raw/notes/*.md`) routinely
contains **verbatim descriptions of engine code changes**, because the
session-end hook captures Claude Code sessions that worked on the engine.
Example block from `daily/2026-05-15.md` that triggered the incident:

> Decisions: scripts/lint.py — `import re` ergänzt, `daily_root_not_digest`
> Branch hinzugefügt. Neues Script `scripts/backfill_daily_rollup.py`. Neues
> Script `scripts/cleanup_legacy_daily_roots.py`.

The compile agent read those decisions as **instructions**. With Write/Edit
authority + cwd=vault + acceptEdits + no settings-sources, it duly
re-implemented the engine changes inside `lxw/.wiki/scripts/` — byte-identical
to the upstream commits already on origin/main. Operator's next `wiki update`
failed with:

```
error: Your local changes to the following files would be overwritten by merge:
        scripts/lint.py
error: The following untracked working tree files would be overwritten by merge:
        scripts/backfill_daily_rollup.py
        scripts/cleanup_legacy_daily_roots.py
```

Classic **prompt injection via substrate**: source content acts as
instruction, agent has filesystem authority over engine, no isolation.

## Short-term mitigations (shipped)

1. `prompts/compile_main_system.md` — explicit SCOPE block: agent may only
   Write/Edit under `knowledge/`. Engine work in source is subject matter, not
   an instruction.
2. `compile.py` — `disallowed_tools=["Edit(.wiki/**)", "Write(.wiki/**)",
   "Edit(daily/**)", "Write(daily/**)", "Edit(raw/**)", "Write(raw/**)"]`.
   Hard tool-level deny enforced by the CLI.
3. `compile.py` — `setting_sources=["project"]` so vault-root `CLAUDE.md`
   (if shipped) reaches the agent. (lxw has no CLAUDE.md yet; backlog item.)

Defense-in-depth — three layers (prompt + tool-deny + settings). One alone
would be insufficient.

## Long-term refactor (not shipped)

Remove the agent's filesystem-write authority entirely. The agent should:

1. Read source + index + facts (via Read/Glob/Grep — keep these).
2. Return the compiled article body + index-row + log-line + people-page
   updates as a structured `ResultMessage` payload (JSON or YAML).
3. `compile.py` deterministically writes the payload to the correct paths
   under `knowledge/`. No agent-side filesystem mutation.

Benefits:

- No prompt injection surface — agent cannot write at all.
- Deterministic file layout — no "agent picked wrong subfolder" failures.
- Easier to audit — single write path, single diff to review.
- Easier to test — feed a fake `ResultMessage` to the writer, no LLM needed.

Costs / open questions:

- The current prompt has the agent edit `knowledge/index.md`,
  `knowledge/log.md`, and `knowledge/people/<slug>.md` in addition to creating
  the article. The structured payload needs to express all four classes of
  output (new article, index row, log line, people-page deltas).
- People-page updates today are Edits in-place (append to `## Action Items`
  section). Structured form: `{ "people_updates": [{"slug": "...", "section":
  "Action Items", "append_lines": [...]}] }`. Writer applies the patch
  idempotently.
- Connection-article creation (`knowledge/connections/*.md`) is the same
  pattern as the main article — payload shape extends naturally.
- Risk: prompt schema drift. Mitigation: Pydantic validation of the payload
  on read, falling back to a clear error rather than silent partial-write.

## Verification (when shipped)

- Synthesize a fake daily/* file that contains `## Decisions` blocks
  describing fictional engine changes (e.g. "modify scripts/foo.py to add
  X"). Compile it. Verify:
  - No files outside `knowledge/` are touched (`git status` clean outside
    `knowledge/` and `state/`).
  - The fictional engine changes appear as DESCRIPTIONS in the compiled
    article, not as actual file edits.
- Replay the 2026-05-15 daily file (the original trigger) and verify lxw's
  `.wiki/scripts/` stays clean.

## References

- Memory: `feedback_no_silent_provider_fallback` — sibling pattern (boundary
  discipline between subsystems).
- KNOWLEDGE.md: add a new entry under `## Gotchas` referencing this backlog
  once the long-term refactor lands.
