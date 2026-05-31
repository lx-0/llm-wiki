# Postcompact-Only SessionStart Injection

**Status:** backlog, optional optimization on top of the 2026-05-05 pointer-block refactor (further reworded 2026-05-30, `3f1da92`, into a framed `<knowledge-base>` block with authority + trigger). Evaluate after ≥2 weeks of pointer-block-as-shipped observation — the observation window restarts on the 2026-05-30 wording.

**Origin:** 2026-05-05 prior-art audit found `yoloshii/ClawMem` runs SessionStart injection **only after compaction** (`source: "compaction"`), not on every session start. Their stated reasoning: *"context-surfacing on first prompt is more precise"* than unconditional SessionStart bootstrapping. Compaction-recovery is the actual failure mode worth fixing; fresh sessions can read `AGENTS.md` (when CWD is the vault) or pull on demand (when CWD is anywhere else).

## Idea

Modify `hooks/session-start.py` to inspect the hook input and short-circuit when `source != "compaction"`. The pointer-block + daily-tail injection only fires when Claude Code is recovering from auto-compaction or `--resume` — i.e. the moments where context was just lost.

For brand-new sessions (`source: "startup"`), the hook returns an empty additionalContext, the agent operates from CWD-resident files (CLAUDE.md, AGENTS.md if applicable, repo state) — same as any other Claude Code session not hooked into a wiki.

## Why it could work

- **The cost of injection is paid even when the session has no use for it.** Most sessions launched from `~/Code/some-project/` have nothing to do with the lxw vault. They still pay for the hook today (sub-50 ms file I/O + an `additionalContext` block of ~600-1200 chars). Conditional firing reduces that to zero except where it matters.
- **Compaction is the actual context-loss event.** A fresh session never had the wiki context to begin with — there's nothing to "restore" at startup. Compaction *did* have it and lost it. Inject precisely there.
- **Aligns with the pointer-block thesis.** We already accepted that the wiki is pull-on-demand. Conditional SessionStart is a natural extension: also *push* only when there's a clear gain.

## Why it might fail / risks

1. **First-prompt-discoverability.** Agents in fresh sessions launched outside the vault won't know the vault exists at all — no pointer, no path, no hint. Until the user mentions it, the agent has no reason to grep it. For sessions that *would have* benefited but didn't because the user assumed the agent knew, this is a regression vs. today's pointer-block.
   - Mitigation: the user knows whether their session is wiki-relevant. They can `@reference` the vault path or include it in a prompt. Same as any other resource not in CWD.
   - Counter-mitigation: that's friction the current hook removes. We'd be re-introducing it.
2. **`source` field reliability.** Need to verify `hookSpecificOutput` for SessionStart actually carries the `source` field consistently across `startup` / `resume` / `compaction` / `clear`. If not, the conditional cannot be implemented cleanly.
3. **Compaction frequency.** If most lxw-aware sessions never compact (short sessions), the savings are smaller than they appear. Long agentic sessions compact often; quick CLI sessions don't. Know the distribution before optimizing.

## Hard preconditions before implementing

- [ ] Verify Claude Code's SessionStart hook input shape — specifically the `source` field across all four trigger types (`startup`, `resume`, `compaction`, `clear`) — via the official hooks reference + a quick smoke test.
- [ ] Have ≥2 weeks of observation data on the pointer-block-as-shipped: how many sessions actually use the injected context? If most don't, this optimization is high-value. If most do, the optimization is irrelevant and may be a regression.
- [ ] Decide whether `source: "resume"` should also fire (resumed sessions kept their context but may have stale daily-tail).

## Configuration shape (sketch)

In `config.yaml`:

```yaml
hooks:
  session_start:
    inject_on_sources: ["compaction"]   # or ["compaction", "resume"], or ["startup", "resume", "compaction", "clear"] for old behaviour
```

Default for v1 of this feature: `["compaction", "resume"]` (paranoid — both are actual context-recovery moments). Pure `["compaction"]` only if observation supports it.

## Non-goals

- Removing the SessionStart hook entirely. The pointer-block at compaction is load-bearing.
- Per-source injection variants (different content for compaction vs. resume). Same content; the difference is just whether to fire at all.
- Coordination with the `prompt-aware-index-injection.md` UserPromptSubmit feature. They are independent: PostCompact-SessionStart restores the *map*, UserPromptSubmit surfaces *specific items*. Both can ship; neither replaces the other.

## Reference

- [ClawMem postcompact-inject hook](https://github.com/yoloshii/ClawMem) — 1200-token budget, content shape: "precompact state + recent decisions + antipatterns + vault context"
- [Anthropic Hooks Reference — SessionStart `source` field](https://code.claude.com/docs/en/hooks)
