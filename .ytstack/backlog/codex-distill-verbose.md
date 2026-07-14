# Codex-session distill quality — tool-heavy sessions render verbose/raw

Status: **backlog** (2026-07-14, observed while verifying the codex-capture fix).

## Problem
Now that Codex sessions are captured (commit `fed2e05`), a heavily tool-driven
Codex session (e.g. `019f5ac6`: 2505 tool calls, mostly `exec_command` /
`apply_patch`) distills into `daily/<date>/sessions.md` as a near-raw dump of
`[exec] …` tool summaries + full `apply_patch` bodies, rather than a clean
Context / Decisions / Lessons distillation. The flush LLM had little assistant
prose to distil (the session was almost all tool execution) and reproduced the
tool activity verbatim, including large inline patch payloads.

## Why it happens
`prompts/` flush-extraction prompt is tuned for Claude-Code sessions where
assistant prose carries the analytical signal. Codex sessions can be
tool-execution-dominated with sparse prose, so the extractor has nothing to
compress and echoes the `[exec]` stream. The per-class budgets
(`build_context`) already cap tool-summary chars, but a session that is ~all
tools still fills the daily block with low-signal command bodies.

## Possible fixes (not yet decided)
- Tighten the flush-extraction prompt to summarise tool ACTIVITY ("edited
  `.ytstack/*`, committed openclaw-fleet CLAUDE.md") instead of quoting
  `apply_patch` bodies.
- Truncate/drop full patch/diff bodies from Codex `custom_tool_call` summaries
  in `hooks/_transcript.py::_summarize_codex_tool` (keep the file list + first
  line, drop the +/- hunk body).
- Lower the tool-summary budget share when a session is tool-dominated (prose
  ratio heuristic).

Low urgency: capture works and is correct; this is output legibility.
Files: `prompts/` (flush extraction), `hooks/_transcript.py`.
