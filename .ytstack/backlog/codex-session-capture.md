# Codex session capture — format-aware transcript ingestion

Status: **in progress** (2026-07-14). Fix for a silent, latent capture failure.

## Problem (verified empirically on lxw)

Codex hooks are installed at user scope (`~/.codex/hooks.json`, `SessionStart` +
`Stop`) and **fire** (Codex `config.toml` `[hooks.state]` carries trusted
hashes for both; `flush.log` shows `Processing session 019f…` for Codex
sessions). But **zero Codex sessions have ever been captured** into the vault:

- 10 distinct Codex sessions in `flush.log` → **all** `Found 0 turns → skipping`.
- Codex rollout ids (`019f…`, UUIDv7) match `~/.codex/sessions/**/rollout-*-<id>.jsonl` exactly.
- `daily/*/sessions.md` contains only Claude (UUIDv4) sessions.
- 121 Codex rollouts on disk (118 in Jul 2026) — heavy active usage, all dark to the wiki.

### Root cause

`hooks/_transcript.py::read_transcript` parses **only the Claude Code JSONL
schema** (`entry["message"]["role"]` ∈ {user, assistant}, `message.content`
blocks). Codex rollout files use a different schema — every line is
`{timestamp, type, payload}` with `type` ∈ {`session_meta`, `event_msg`,
`response_item`, `turn_context`, `world_state`, `compacted`, …}. **0 of 1238
lines** in a sample rollout have a top-level `message` object, so the reader
extracts 0 turns and the hook skips the flush. No error; health check stays
green (it only verifies hooks are *wired*, not that capture *succeeds*).

Secondary: `flush.log` also shows 287× `Transcript not found` — Codex's `Stop`
hook sometimes passes a `transcript_path` the reader can't resolve. Net effect
identical: nothing captured.

### Multi-fire complication

Codex has **no `SessionEnd` event** (its hook vocabulary mirrors Claude Code:
`SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PreCompact,
PostCompact, SubagentStart, SubagentStop, Stop` — no once-per-session end). The
engine maps Codex `Stop` → `session-end.py`, and `Stop` fires **per turn**
(measured: one 24 h session → 18 fires, 31 user turns). A naive parser-only fix
would therefore re-flush the whole growing conversation on every turn and append
N duplicate blocks per session.

## Design

### 1. Format-aware transcript ingestion (`hooks/_transcript.py`)
- `read_transcript(transcript_path, session_id=None)` becomes a dispatcher:
  resolve the path → sniff format → parse with the matching reader.
- `_read_claude_transcript` = the existing logic, unchanged.
- `_read_codex_transcript`: canonical, de-duplicated streams —
  - **user** prose ← `event_msg` / `user_message`.`message` (clean prompt; the
    `response_item`/`message` role=user variant is polluted with the injected
    AGENTS.md / environment context and is skipped).
  - **assistant** prose ← `response_item` / `message` role=assistant,
    `output_text` content items.
  - **tools** ← `response_item` / {`function_call`, `custom_tool_call`,
    `web_search_call`, `tool_search_call`} + their `_output` variants, attached
    to the nearest assistant turn (one-line summaries, parity with the Claude
    tool summariser).
  - **skipped**: `developer`/`system` messages (instructions), `reasoning`
    (encrypted), `session_meta`, `turn_context`, `world_state`, `compacted`,
    `inter_agent_communication_metadata`, and all other `event_msg` types
    (streaming duplicates of the above).
- `_detect_format(path)`: reads the first non-empty lines; Codex if a line has
  a top-level `type` in the Codex vocab with a `payload`; Claude if a line has a
  `message` object with a role. Defaults to Claude (back-compat).

### 2. Robust resolution
- `resolve_transcript(transcript_path, session_id)`: if `transcript_path`
  exists, use it; else glob `<codex_home>/sessions/**/rollout-*-<session_id>.jsonl`
  (`codex_home` = `$CODEX_HOME` or `~/.codex`), newest match. Fixes the
  `Transcript not found` class.

### 3. Multi-fire coalescing
- `flush_pipeline.append_to_daily` wraps each session's block in
  `<!-- wiki:session <id> begin -->` … `<!-- wiki:session <id> end -->` and
  **replaces** an existing same-session block in today's file instead of
  appending. One block per session per day, always the latest state. Benign for
  Claude (one flush per session anyway).
- Cost bound: `scheduling.dedup_window_seconds` 60 → 900 (value-migration,
  MODEL_UPGRADES-style — bump only if still at the old default). Within the
  window a re-fire is skipped (block frozen); after it, re-distill + replace.
  Bounds a heavy multi-hour Codex session to ~1 distill / 15 min of activity.
  `build_context` already caps the distill input at ~70 KB regardless of the
  35 MB rollout, so each distill is bounded.

## Deployment
Engine-side only — the operator's `~/.codex/hooks.json` is already correct and
stays as-is (Codex has no better event than `Stop`). Ships via `wiki update`
(+ `migrate_config_keys` for the dedup-window bump).

## Known limitations
- Gemini / Cursor use the same hooks; if their transcript schema is neither
  Claude nor Codex they'd hit the same 0-turns skip. Not fixed here (no local
  data to build/test against) — the dispatcher is extensible when it surfaces.
- `response_item`/`agent_message` (Codex sub-agent inter-comms) is skipped;
  main user/assistant/tool stream is the captured signal.
