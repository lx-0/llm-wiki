---
milestone: M004
slice: S01
project: llm-wiki
created: 2026-05-02T22:00:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M004-S01 — Core agent-task framework

**Goal:** Operators can run `wiki agent <id>` and get a working Claude Agent SDK invocation driven by `prompts/agent_<id>.md` frontmatter. No concrete tasks yet — that's S02.

## What "done" looks like

- A new file `prompts/agent_<id>.md` with valid frontmatter (`model`, `allowed_tools`, `permission_mode`, `max_turns`, `cwd`, optional `button`) is parseable and runnable.
- `scripts/agent_task.py` resolves spec → spawns SDK → streams result → persists log to `.wiki/logs/agent-<id>-<ts>.log` → writes `applied: <iso>` back to the prompt file's frontmatter (similar to `correct_apply.py`'s pattern).
- `wiki agent --list` enumerates task IDs + titles + button presence.
- `wiki agent <id> [--dry-run] [--var key=value]` works.
- pytest tests cover frontmatter parsing (valid + invalid specs) and CLI dispatch (mocked SDK).

## Tasks

- [ ] T01 — Frontmatter spec + parser. New `scripts/agent_spec.py` with `AgentSpec` dataclass (matches the wiki_config pattern), `parse_spec(path)` reads + validates, raises clear errors for missing required fields, supports `${var}` substitution at render time. Tests: 5–8 cases (valid, missing field, unknown tool, invalid permission_mode, malformed YAML).
- [ ] T02 — `scripts/agent_task.py` runner. Wraps Claude Agent SDK call (analog to `correct_apply.py` / `compile.py`). Reads spec via T01 parser, renders body via `prompts.py:render`, spawns SDK, streams ResultMessage to log file, updates frontmatter `last_run: <iso>` on success. CLI args: `<id>` positional, `--dry-run`, `--var key=value` (repeatable).
- [ ] T03 — `wiki agent` CLI dispatcher. New bash command in `wiki` that delegates to `scripts/agent_task.py`. Help block lists examples. `wiki agent --list` enumerates `prompts/agent_*.md` files (id, title from frontmatter, button presence). Wired into top-level case + entry-point banner.
- [ ] T04 — Tests + smoke. pytest module `tests/test_agent_task.py` covers: parser happy + sad paths, dispatcher CLI args parsing, mocked SDK call asserts allowed_tools propagated correctly. Smoke: `wiki agent --list` runs without error against the empty `prompts/agent_*` glob.

## Files touched

- NEW: `scripts/agent_spec.py`, `scripts/agent_task.py`, `tests/test_agent_task.py`
- MODIFY: `wiki` (CLI), `scripts/config.py` (PROMPTS_DIR if not present), `pyproject.toml` (no new deps expected — yaml + dataclasses + pathlib already there)

## Verification

```bash
cd .wiki && uv run pytest tests/test_agent_task.py -v
./wiki agent --list   # expect: "(no agent tasks defined yet)"
./wiki agent --help   # expect: usage block
```

## Out of scope (deferred)

- Concrete tasks → S02
- Dashboard button auto-wiring → S03
- Per-task scheduling / piggyback / locking → backlog (post-M004)
