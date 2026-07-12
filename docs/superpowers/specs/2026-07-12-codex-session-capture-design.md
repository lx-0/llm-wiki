# Codex Session Capture Design

## Problem

The hook installer already writes `SessionStart` and `Stop` entries for Codex,
but the shared transcript reader only understands Claude Code JSONL entries
with a top-level `message` object. Codex 0.144 writes rollout JSONL using
`type` plus `payload`, so the current `Stop` hook finds zero turns.

Codex `Stop` is turn-scoped, not thread-scoped. Re-reading the entire rollout
on every `Stop` would repeatedly compile the same conversation and would also
collide with the flush pipeline's session-level deduplication.

## Goal

Capture every completed Codex turn from every project into the existing
`daily/<date>/sessions.md -> compile -> knowledge/` pipeline without changing
Claude Code behavior or copying raw transcripts into the vault.

## Design

### Transcript normalization

`hooks/_transcript.py` remains the single normalization boundary. It detects
Claude Code entries by their top-level `message` object and Codex entries by
their rollout `type`/`payload` shape.

For Codex, `read_transcript(path, turn_id=...)` starts at the matching
`turn_context` entry and stops at the matching `task_complete` entry or EOF.
This intentionally excludes developer/user context injected before
`turn_context`, including repeated `AGENTS.md` payloads. Within the turn it
normalizes:

- `response_item.payload.type == "message"` with user/assistant roles;
- `input_text` and `output_text` blocks as prose;
- `custom_tool_call` and `custom_tool_call_output` as bounded tool summaries;
- malformed lines, reasoning entries, metadata, and unsupported roles as
  ignorable input.

The normalized output remains `list[Turn]`, so the existing per-class budgets
and flush extractor do not change.

### Turn identity and deduplication

For a Codex `Stop` payload, `hooks/session-end.py` uses `turn_id` as the staged
flush identifier. Codex turn IDs are globally unique UUIDs, so consecutive
turns in one thread no longer collide with the session-level dedup window.
Claude Code continues to use `session_id` unchanged.

Codex keeps the existing `SessionStart` and `Stop` hooks. `PreCompact` is not
required for Codex capture because every completed turn is already flushed;
installing it would introduce a second capture path for the same in-flight
turn.

### Configuration and documentation

The existing global `~/.codex/hooks.json` install target remains correct. The
stale CLI help entry `Start` is corrected to `SessionStart`, and feature docs
state that Codex capture is turn-scoped and format-adapted.

## Failure behavior

- Missing transcript, missing turn, and malformed JSONL fail soft and log zero
  turns, matching current hook behavior.
- Flush extraction failures continue through the existing failed-flush archive
  and retry pipeline.
- Hook work stays below the 10-second budget: JSONL reading, normalization,
  staging, and background process spawn only.

## Verification

1. Unit-test Claude compatibility and Codex turn isolation with synthetic JSONL.
2. Unit-test Codex tool-call normalization and malformed-line handling.
3. Unit-test turn-scoped capture IDs and the generated Codex hook payload.
4. Run focused pytest, the full Python test suite, `ruff`, and `bash -n`.
5. Install global Codex hooks, trust them through Codex if prompted, and run a
   real disposable Codex turn to confirm a new daily session entry.

## Non-goals

- Persisting raw Codex rollouts in `raw/`.
- Capturing hidden reasoning.
- Changing flush prompts, compiler prompts, or vault-specific configuration.
- Altering Claude Code, Gemini, or Cursor transcript formats.
