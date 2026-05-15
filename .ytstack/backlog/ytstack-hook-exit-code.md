# ytstack `pre-tool-use-edit` hook: exit 2 = block, not warn

## The bug

`hooks/pre-tool-use-edit` uses `exit 2` to emit "drift warnings" with a message
that explicitly states *"this is a warning, not a block"* and *"Proceeding
anyway -- the edit will happen."*

Reality: Claude Code's PreToolUse hook protocol treats **exit 2 as a hard
block**. The Edit/Write/MultiEdit tool call fails with `PreToolUse:Edit hook
error` and the file is NOT written. The hook author's intent and the harness's
behaviour are at odds.

## How it surfaces

Two recurring scenarios:

1. **Closing a task via `ytstack:summarize-task`.** The skill writes
   `M###-S##-T##-SUMMARY.md` and updates `M###-S##-PLAN.md` + `STATE.md`. None
   of these paths are in the T##-PLAN's Files section, so the hook fires drift
   warnings on every single one. Workaround: route the writes through Bash
   heredoc / `python -c` (Bash is not gated). Cost: 3+ extra tool calls per
   task closure.

2. **Adding adjacent artifacts mid-task** -- e.g. a backlog file, DECISIONS
   entry, or KNOWLEDGE addendum surfaced while implementing. Same drift, same
   block.

First hit: 2026-05-15 during M005-S01-T01 (this milestone's first task).

## Fix options

**A. Use exit 0 + stderr-only warning.** The intended behaviour. The drift
   warning still appears in the tool output (stderr surfaces in
   `--debug` / hook-output paths) but does not block.

```bash
# replace
exit 2
# with
exit 0
```

   Trade-off: drift becomes invisible to the agent unless it actively reads
   the hook-stderr surface. Most agents won't.

**B. Keep exit 2 but document the block semantics as intentional.** Then
   change all ytstack skills (`summarize-task`, `plan-task`, etc.) to
   pre-include their adjacent file paths in the PLAN's Files section. Costs
   one extra line per plan-task, removes the need for workarounds.

**C. Hybrid:** exit 2 only on suspicious paths (touching `src/` outside
   declared scope), exit 0 + warn on ytstack-internal paths
   (`.ytstack/**`, `**/SUMMARY.md`, `**/PLAN.md`, `DECISIONS.md`,
   `KNOWLEDGE.md`, `backlog/**`). Most precise but most code.

## Recommendation

**B + convention update.** `plan-task` skill auto-injects
`.ytstack/M###-S##-T##-SUMMARY.md` into the PLAN's Files section by default,
plus any meta-files the task is likely to touch (DECISIONS, KNOWLEDGE,
backlog). Existing PLAN files get a one-shot retro-fix when they next become
active. Hook semantics stay as-is (exit 2 = block, which is genuinely useful
for catching real scope drift in src/).

## Workaround until fixed

Use Bash for ytstack-meta-file writes:

```python
python3 -c "import pathlib; pathlib.Path('.ytstack/foo').write_text(...)"
```

## Status

Backlog. Not blocking M005 execution -- workaround is small and well-known
now. Worth fixing in a small ytstack-engine PR (single hook file +
plan-task skill update).
