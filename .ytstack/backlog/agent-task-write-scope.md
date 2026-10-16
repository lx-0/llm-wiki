# Agent tasks run with `acceptEdits` and no write scope on substrate input

**Status:** open, security-relevant. Recorded 2026-10-16 (M034-S06-T06), found while
correcting `prompts/agents/dream-cycle.md`.

**What the code does:** `scripts/agent_task.py` passes each spec's `allowed_tools` and
`permission_mode` straight to `run_sdk_query`, with no `write_scope` ("agent tasks
self-declare their sandbox — no engine path-scope hook, so `permission_mode=acceptEdits`
specs behave as before"). Four specs in `prompts/agents/` declare `permission_mode:
acceptEdits` with Write/Edit: `daily-digest`, `dream-cycle`, `orchestrate-tasks`,
`summarize-day`. They read substrate (`daily/**`, `raw/**`), and two of them run unattended
(`daily_digest_yesterday` piggyback) or from a dashboard button.

**Why it matters:** AGENTS.md's HARD rule (locked 2026-05-15) says any SDK call that feeds
substrate with Write/Edit tools needs three layers: a prompt-level scope, a PreToolUse path
scope through `SdkCallSpec(write_scope=…)`, never `acceptEdits`, and
`setting_sources=("project",)`. The rule exists because substrate carries literal
change-descriptions from engine sessions, which an agent with write authority acts on
(KNOWLEDGE "Compile prompt injection via substrate"). The agent-task path is the one SDK
path the rule does not reach.

**Direction (recommended):**
- `AgentSpec` gains a `write_scope:` frontmatter list, the roots the agent may write.
  Examples: `daily/` for daily-digest; `knowledge/people/`, `knowledge/projects/` and
  `knowledge/areas/` for dream-cycle; `workspace/` for orchestrate-tasks.
- `agent_task.py` passes it as `SdkCallSpec(write_scope=WriteScope(roots=…))`. It refuses a
  spec with Write/Edit and no scope, and drops `acceptEdits` for the default mode with the
  hook.
- A test parses every spec in `prompts/agents/` and fails on Write/Edit without
  `write_scope`.

Decide whether `orchestrate-tasks` (which executes operator-accepted tasks) needs a
wider scope than its record files, before applying the rule there.
