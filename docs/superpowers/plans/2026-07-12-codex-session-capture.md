# Codex Session Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture each completed Codex turn into the existing LLM Wiki session pipeline while preserving Claude Code behavior.

**Architecture:** Extend the transcript normalization seam to understand Codex rollout JSONL and isolate one `turn_id` at a time. Use the Codex turn ID as the flush identity so turn-scoped `Stop` hooks do not collide or recompile the full thread.

**Tech Stack:** Python 3.11+, pytest, Bash/jq hook installer, existing `Turn` and `flush_pipeline` abstractions.

## Global Constraints

- Do not modify vault prompts or `config.yaml`.
- Keep hook foreground work below 10 seconds and spawn heavy extraction in the background.
- Preserve existing Claude Code transcript behavior byte-for-byte where practical.
- Never persist hidden reasoning from Codex rollouts.
- Stage and commit only feature files; leave the operator's local `scripts/compile_stages/route.py` change uncommitted.

---

### Task 1: Normalize Codex rollout turns

**Files:**
- Modify: `hooks/_transcript.py`
- Create: `tests/test_codex_transcript.py`

**Interfaces:**
- Consumes: Codex rollout JSONL entries and optional `turn_id: str`.
- Produces: `read_transcript(transcript_path: str, *, turn_id: str | None = None) -> list[Turn]`.

- [ ] **Step 1: Write failing parser tests**

Create synthetic rollout entries with `turn_context`, user/assistant messages,
tool calls, tool outputs, and `task_complete`. Assert that a requested turn:

```python
turns = read_transcript(str(path), turn_id="22222222-2222-2222-2222-222222222222")
assert [(turn.role, turn.text) for turn in turns if turn.text] == [
    ("user", "Implement Codex capture"),
    ("assistant", "Implemented and verified"),
]
assert "[exec]" in "\n".join(tool for turn in turns for tool in turn.tools)
assert "AGENTS payload" not in build_context(turns)
```

Also retain one Claude-format regression test and malformed JSONL coverage.

- [ ] **Step 2: Run the tests and verify the Codex cases fail**

Run: `uv run pytest tests/test_codex_transcript.py -v`

Expected: Codex cases fail because `read_transcript` ignores `payload` entries
or does not accept `turn_id`; Claude regression passes.

- [ ] **Step 3: Implement format detection and Codex normalization**

Add focused helpers:

```python
def _split_codex_content(content: object) -> tuple[str, list[str]]: ...
def _read_claude_entries(entries: list[dict]) -> list[Turn]: ...
def _read_codex_entries(entries: list[dict], turn_id: str | None) -> list[Turn]: ...
def read_transcript(transcript_path: str, *, turn_id: str | None = None) -> list[Turn]: ...
```

Select Codex entries from the matching `turn_context` through matching
`task_complete`/EOF. Ignore `reasoning`, developer roles, and pre-context
injected messages. Normalize `custom_tool_call` and
`custom_tool_call_output` into bounded tool summaries.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_codex_transcript.py tests/test_transcript_budgets.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the parser change**

```bash
git add hooks/_transcript.py tests/test_codex_transcript.py
git commit -m "fix: parse Codex rollout transcripts"
```

---

### Task 2: Make Codex Stop captures turn-scoped

**Files:**
- Modify: `hooks/session-end.py`
- Create: `tests/test_codex_hook_capture.py`

**Interfaces:**
- Consumes: hook input fields `hook_event_name`, `session_id`, `turn_id`, and `transcript_path`.
- Produces: `capture_id_for_hook(hook_input: dict) -> str` and one staged flush per Codex turn.

- [ ] **Step 1: Write failing identity tests**

Load `hooks/session-end.py` through `importlib.util` and assert:

```python
assert capture_id_for_hook({
    "hook_event_name": "Stop",
    "session_id": "session-id",
    "turn_id": "turn-id",
}) == "turn-id"
assert capture_id_for_hook({
    "hook_event_name": "SessionEnd",
    "session_id": "session-id",
}) == "session-id"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/test_codex_hook_capture.py -v`

Expected: failure because `capture_id_for_hook` does not exist.

- [ ] **Step 3: Implement turn-aware capture**

Add:

```python
def capture_id_for_hook(hook_input: dict) -> str:
    if hook_input.get("hook_event_name") == "Stop" and hook_input.get("turn_id"):
        return str(hook_input["turn_id"])
    return str(hook_input.get("session_id", "unknown"))
```

Pass `turn_id` into `read_transcript`, and use the derived capture ID for
staging, logging, and the spawned `flush.py` argument. Keep Claude behavior
unchanged when `turn_id` is absent.

- [ ] **Step 4: Run focused hook and parser tests**

Run: `uv run pytest tests/test_codex_hook_capture.py tests/test_codex_transcript.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the hook change**

```bash
git add hooks/session-end.py tests/test_codex_hook_capture.py
git commit -m "fix: capture Codex turns independently"
```

---

### Task 3: Pin the installer contract and update docs

**Files:**
- Modify: `lib/agents.sh`
- Modify: `wiki`
- Modify: `docs/FEATURES.md`
- Modify: `docs/cli.md`
- Create: `tests/test_agent_hooks.py`

**Interfaces:**
- Consumes: `codex_hooks_payload` from `lib/agents.sh`.
- Produces: user-scope `~/.codex/hooks.json` containing `SessionStart` and `Stop` commands.

- [ ] **Step 1: Write a failing/stability test for the payload**

Source `lib/agents.sh` in a subprocess with a temporary `WIKI_DIR`, parse the
JSON, and assert:

```python
assert set(payload["hooks"]) == {"SessionStart", "Stop"}
assert "session-start.py" in payload["hooks"]["SessionStart"][0]["hooks"][0]["command"]
assert "session-end.py" in payload["hooks"]["Stop"][0]["hooks"][0]["command"]
```

- [ ] **Step 2: Run the payload test**

Run: `uv run pytest tests/test_agent_hooks.py -v`

Expected: the payload contract passes; the test protects the already-correct
installer while documentation is corrected.

- [ ] **Step 3: Correct comments and documentation**

State that Codex uses `SessionStart` plus turn-scoped `Stop`, that transcript
normalization supports Codex rollout JSONL, and that Codex intentionally does
not install `PreCompact` because completed turns are already captured.

- [ ] **Step 4: Run syntax and focused tests**

Run: `bash -n wiki lib/agents.sh lib/hooks.sh`

Run: `uv run pytest tests/test_agent_hooks.py tests/test_codex_transcript.py tests/test_codex_hook_capture.py -v`

Expected: shell syntax succeeds and all focused tests pass.

- [ ] **Step 5: Commit installer docs and contract test**

```bash
git add lib/agents.sh wiki docs/FEATURES.md docs/cli.md tests/test_agent_hooks.py
git commit -m "docs: clarify Codex hook lifecycle"
```

---

### Task 4: Verify, install globally, and publish

**Files:**
- External configuration: `~/.codex/hooks.json` (not committed)

**Interfaces:**
- Consumes: completed feature branch and active vault path.
- Produces: trusted global Codex hooks plus a draft GitHub PR.

- [ ] **Step 1: Run repository verification**

Run: `uv run pytest -q`

Run: `uv run ruff check hooks tests/test_codex_transcript.py tests/test_codex_hook_capture.py tests/test_agent_hooks.py`

Run: `bash -n wiki lib/agents.sh lib/hooks.sh`

Expected: all commands exit zero.

- [ ] **Step 2: Inspect feature-only diff**

Run: `git status -sb` and `git diff origin/main...HEAD --stat`.

Expected: the operator's `scripts/compile_stages/route.py` remains unstaged and
absent from the branch diff.

- [ ] **Step 3: Install global Codex hooks**

Run the existing installer for Codex at user scope, confirm
`~/.codex/hooks.json` parses, and verify `wiki hooks status` reports Codex as
installed. Review/trust the hook through `/hooks` in Codex when prompted.

- [ ] **Step 4: Run an end-to-end smoke turn**

Start a disposable Codex task, complete one turn, and verify that the hook log
reports a non-zero turn count and stages/appends a new daily session without
printing conversation content.

- [ ] **Step 5: Push and open a draft PR**

```bash
git push -u origin codex/codex-session-capture
gh pr create --draft --base main --head codex/codex-session-capture
```

PR body: root cause, turn-scoped design, files changed, verification commands,
and note that vault configuration/prompts plus the local `route.py` patch were
not included.
