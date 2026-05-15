# LLM transcripts collector — operator's own LLM conversations as substrate

**Priority:** P2 — probably the single largest unused signal in the operator's
digital life. Claude Code alone produces hundreds of MB of structured JSONL on
this machine. Currently zero coverage.

**Origin:** 2026-05-15 substrate-landscape conversation. Identified as the
heaviest "what does the operator actually think about" corpus that the wiki
ignores.

## The gap it fills

The operator's questions, half-thoughts, mid-session reformulations, decisions
overruled, and debugging narratives all flow through LLM chats — and almost
none of it lands in the wiki. compile.py distills daily/ entries (post-hoc
summary) but the conversational substrate where the actual thinking happened
is invisible.

This is meta-substrate: the operator's voice talking to a machine, often more
unfiltered than they'd write in a daily log.

## Source landscape

| Source | Format | Live or export | Access notes |
|---|---|---|---|
| Claude Code | JSONL per project at `~/.claude/projects/<encoded-cwd>/*.jsonl` | Live (already on disk) | Structured: messages, tool calls, file edits, model id. Cheap to read. |
| Cursor | SQLite (`~/Library/Application Support/Cursor/User/workspaceStorage/.../state.vscdb`) | Live | Less structured; workspace-bound. Needs schema reverse-engineering. |
| Claude.ai (web) | ZIP export from claude.ai/settings | Manual export | No API. Drop-folder pattern: operator dumps export, collector ingests. |
| ChatGPT | ZIP export from chatgpt.com/settings | Manual export | Same drop-folder pattern. |
| Aider / Codex / other CLI agents | Varies — JSONL, plain log, none | Mostly live | Only if operator uses these. Defer. |

## Substrate boundary

Sessions are operator-content (their questions are theirs; the LLM's responses
are derivative). Substrate class = meta. Lands in `raw/transcripts/llm/`
mirroring `raw/transcripts/jamie/` and `raw/transcripts/gmeet/`.

One file per session — not per JSONL line. Filename convention:
`raw/transcripts/llm/<source>-<YYYYMMDD>-<short-id>.md` (e.g.
`raw/transcripts/llm/claudecode-20260515-abc12.md`).

## Phasing

**Phase 1 — Claude Code only.** Already on disk, already structured, no auth,
no manual export. Walk `~/.claude/projects/`, group JSONL files by project,
emit one md per session. Frontmatter: `source`, `project`, `started_at`,
`ended_at`, `message_count`, `tool_call_count`, `models_used`. Body: rendered
markdown of the conversation, with tool calls collapsed (the file edits matter,
not the bash `ls` calls).

**Phase 2 — Cursor.** Once Phase 1 producer-quality is proven on compile.py.
Needs schema reverse engineering on Cursor's `state.vscdb`.

**Phase 3 — Claude.ai + ChatGPT exports.** Drop-folder ingest. Operator runs
manual export quarterly, drops ZIPs into `<vault>/inbox/llm-exports/`, collector
unpacks + ingests. No live polling possible.

## Volume problem (the real risk)

Claude Code alone is GB-scale of JSONL. Compiling every session into the
knowledge graph would overwhelm the substrate. Filtering is mandatory:

- **Session-length threshold.** Drop sessions shorter than N messages or N
  minutes — those are exploratory pings, not thinking.
- **Tool-call density.** Sessions that are 95% bash/grep are workflow, not
  thinking. Sessions dense in human prose are higher signal.
- **Project allowlist.** Only ingest sessions from certain repos? Or weight
  them differently? Probably allowlist-with-default-deny.
- **Operator-flagged sessions.** A `wiki llm star <session-id>` CLI to mark
  sessions worth keeping; rest get dropped or summary-only.
- **LLM-pre-distill before compile.** Run a cheap local model (Ollama) over
  each session to produce a 1-paragraph summary; ingest the summary, not the
  raw. compile.py then distills summaries, not 50k-token transcripts.

The pre-distill route is probably the only sustainable shape. Worth a
mini-pitch in its own right.

## Anti-slop heuristics

- Min N user messages
- User-message-to-tool-call ratio > threshold
- Session contains at least one `wiki`-CLI invocation, OR
- Session is in operator-flagged project, OR
- Session was explicitly starred

## Open questions

- **Privacy.** Some sessions contain secrets / proprietary client code that
  shouldn't land in any wiki, even private. Redaction step? Project denylist?
- **Multi-machine.** Operator works on multiple machines. Does each machine's
  collector ingest its own transcripts, or sync to a central pool first?
- **Cursor session ID.** Cursor's SQLite schema — does it have stable session
  IDs we can use for delta-ingest watermarks?
- **Granularity.** One file per session, or one file per project per day
  (concatenated sessions)? Per-session feels right but generates a lot of
  small files.

## Touchpoints

- `scripts/collectors/llm_transcripts.py` — new collector. Phase 1: Claude Code
  JSONL walker. `supports_account_loop=False` initially.
- `scripts/collectors/llm_transcripts_distill.py` — separate module if the
  pre-distill route is taken; uses local Ollama via the `local-llm` skill.
- New limit configs: `llm_transcripts_min_messages`, `llm_transcripts_min_minutes`.
- compile.py — likely no changes if pre-distill produces normal markdown.

## Lift estimate

- Phase 1 walker (Claude Code only, no pre-distill): 1 day
- Phase 1 + pre-distill via Ollama: 2-3 days
- Phase 2 Cursor: 1-2 days after schema reverse-engineering
- Phase 3 drop-folder for web exports: 0.5 day

**~3-4 days for Phase 1 with pre-distill** which is the only meaningful version.

## Risks

1. **Volume blows up the wiki.** Without pre-distill, every session becomes a
   raw file the compile pass tries to consume. Mitigation: pre-distill is the
   default mode, raw-only behind explicit flag.
2. **Pre-distill loses the operator's actual voice.** Summaries average out the
   exact phrasings that make this corpus distinctive. Mitigation: pre-distill
   prompt explicitly preserves operator quotes verbatim.
3. **Privacy leak.** A starred session ingests secrets/IP from a client repo.
   Mitigation: per-project denylist; redaction pass for known secret patterns
   (Bearer tokens, API keys); read-only ingest does not exfiltrate.
4. **Schema drift.** Anthropic changes Claude Code JSONL format. Mitigation:
   pin to specific keys (`type`, `role`, `content`), fail-soft on unknown shapes.

## Ripens when

- Operator wants the wiki to answer "what was I debugging in February?" and
  realizes it has zero context because no daily/ entry captured that arc.
- OR pre-distill prompt is proven viable on a small sample (10 sessions).
- OR Cursor session inspection becomes a felt need (less likely — Claude Code
  dominates the operator's LLM usage).

## Status

Backlog. Highest-yield substrate by raw signal density, but the highest-risk
by volume. Pre-distill design is the gating decision — without it, do not start.
