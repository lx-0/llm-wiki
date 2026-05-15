# Compile silent-fail at ≥60 KB source — different from buffer-limit class

**Triggered by:** 2026-05-13 Jamie transcript compile audit. After fixing the 1 MB stream-json buffer (commit `70d2fef`), a 35 KB transcript compiles cleanly but a 60 KB one fails reproducibly with a DIFFERENT class of crash.
**Priority:** P1 — blocks ingest of any large source (60 KB+ Jamie meetings, large daily logs, big screenshot batch reports).

## Observed data (2026-05-13)

| File | Size | Result | Duration | Cost | Profile |
|---|---|---|---|---|---|
| `alex-x-sid-3-3` | 9 KB | ✓ | 5:28 | $0.03 | in:106 out:1,248 — normal |
| `alex-x-sid-1-3` | 35 KB | ✓ (post-buffer-fix) | 5:47 | $0.05 | in:92 out:1,854 — normal |
| `alex-x-sid-2-3` | 60 KB | ✗ | 4:11 | $0.00 | **in:0 out:0, exit-1, empty stderr** |
| `alex-x-sid-2-3` (re-run) | 60 KB | ✗ | 8:46 | $0.00 | **in:0 out:0, exit-1, empty stderr** |

**Failure profile:**
- The bundled CLI runs for 4–9 minutes (variable, not deterministic timing)
- Emits **zero parseable stream-json messages** (compile.py's `total_input_tokens` / `total_output_tokens` stay at 0 the whole run → `cost: $0.0000`)
- Exits with code 1, writes nothing to stderr (`[CLI-STDERR] (empty)`)
- The SDK raises `ProcessError("Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details")` from `claude_agent_sdk._internal.transport.subprocess_cli`

Not the 1 MB stream-json buffer class — that one was diagnosed via the explicit `Failed to decode JSON: ... exceeded maximum buffer size of 1048576 bytes` exception. With `CONFIG.limits.sdk_max_buffer_size_mb=50` in place, this new class still trips.

## Hypotheses (ranked)

1. **Output-side scale**: Opus is doing big tool-call cascades (Read on `knowledge/index.md` repeatedly, Write/Edit on many articles) and the CLI accumulates message state that eventually breaks. The 60 KB source produces a larger fan-out of concepts than 35 KB, so more tool calls, more memory pressure.
2. **Max-turns cliff**: `max_turns=30` in compile.py. A 60 KB meeting may need >30 turns and hit the cap; the CLI's handling of max-turns-hit emits no ResultMessage on this code path (would be a CLI bug).
3. **Anthropic API safety/refusal**: Some content in the 60 KB transcript triggers a refusal from Claude. The CLI handles refusal by exiting 1 without bubbling the reason up via stream-json. (Would be another CLI bug — refusals should be ResultMessages.)
4. **Mid-stream memory limit in CLI subprocess**: macOS resource-limit hit despite 64 GB RAM available. ProcessError exit-1 without stderr matches a SIGKILL profile.
5. **Long-stall internal timeout**: CLI has its own internal idle/inactivity timeout that fires after 4-9 min of API silence (e.g. Opus thinking).

## Proposed investigation order

1. **Try `--max-turns 50` or higher**: cheap probe to falsify hypothesis 2.
2. **Try smaller model** (Sonnet via `--model claude-sonnet-4-6` ad-hoc): if it succeeds, hypothesis 1 or 3 (Opus-specific resource ceiling or safety).
3. **Split the 60 KB file in two halves**: if both halves succeed, size-related (1, 4); if one specific half fails, content-trigger (3, content-class).
4. **Enable verbose CLI logging** via env var (`CLAUDE_DEBUG=1` / `CLAUDE_LOG_LEVEL=debug` / whatever the bundled CLI honors): may surface the silent crash cause.
5. **Try the 75 KB Bad Nauheim Workshop**: if it also fails, deeply confirm size class. If it succeeds, the 60 KB transcript has some specific content trigger.

## Acceptance criteria

- [ ] Root cause identified with a deterministic reproducer
- [ ] Either: fix landed, or a documented workaround (e.g. "files >50 KB are compiled with Sonnet" or "files >50 KB are pre-chunked to halves")
- [ ] KNOWLEDGE.md entry added under "Hard-won learnings"
- [ ] Acceptance test: the failing 60 KB file compiles cleanly

## Adjacent

- `.ytstack/KNOWLEDGE.md` "Claude Agent SDK silently crashes on >1 MB stream-json messages (2026-05-13)" — closely-related but different class. Same exit-1-empty-stderr surface, different mechanism.
- `.ytstack/backlog/compile-per-call-timeout.md` — proposes `asyncio.wait_for` per-message-stall timeout. Would convert the current 4-9 min silent stall into a logged timeout, surfacing this failure mode earlier.

## 2026-05-15 update: partial fix landed, full root-cause still open

New data point: lxw `gmeet/2026-05-13--...--1qvzqCWczl6u.md` (138 KB) failed with the same exit-1 / empty stderr profile after 793 s. Re-checking the 2026-05-13 ranking:

| File | Size | Result | Notes |
|---|---|---|---|
| sid-3-3 | 9 KB | ✓ | |
| sid-1-3 | 35 KB | ✓ | |
| sid-2-3 | 60 KB | ✗ (then) | |
| Bad Nauheim Workshop 3-3 | 75 KB | ✓ | succeeded 2026-05-13 19:01 — so size alone is not the discriminator |
| gmeet 2026-05-13 | 138 KB | ✗ | |

So failure is **non-monotonic in size** — a 60 KB file can fail while a 75 KB file succeeds. Strengthens hypothesis 1 (tool-turn fan-out, not raw size) over hypothesis 4 (resource ceiling).

**Partial fix (commit pending, 2026-05-15):**
- `compile.py` now wires `assert_prompt_within_budget` (`compile_max_prompt_chars: 400_000`) — catches truly oversized initial prompts before the SDK call. The 138 KB case currently fits.
- `max_turns` dropped from 30 to 12 (`compile_max_turns`) — caps tool-turn ballooning, which is the suspected real driver. A model on a huge source that wants to Read+Grep 25 articles will instead commit at 12 turns. May trigger `error_max_turns` on legitimately-deep compiles; if observed, raise to 15-18.
- INFO line on sources ≥ 50 KB so the operator sees *which* file slowed things down without re-reading the error log.

**Still open:** confirm 138 KB compiles cleanly under the new caps, and characterize whether `max_turns=12` is too tight for any other historic-success workload. If the 138 KB still fails, drop to splitting the transcript at meeting-section boundaries pre-compile.

## Operator workaround for now

- The new pre-flight + max_turns cap should let `wiki compile` chew through the 138 KB case at known cost (or abort cleanly with `error_max_turns` instead of silent burn). Validate on the next lxw run.
- Fallback if it still fails: split sources >100 KB at section boundaries before placing under `raw/transcripts/`.
