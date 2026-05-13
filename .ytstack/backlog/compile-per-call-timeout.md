# compile.py — per-call timeout on SDK query()

**Status:** backlog. Real bug, surfaced 2026-05-10. Independent fix, no preconditions.

## Problem

`compile.py:217` and `:307` invoke `claude_agent_sdk.query()` with no per-call timeout. The SDK in turn spawns the bundled Claude Code CLI as a subprocess and waits on its stdout stream-json. If the subprocess **hangs** (vs crashes), there is no upper bound: the parent python keeps waiting forever.

**Observed 2026-05-10 incident:**
- Compile run started 13:34. Reached `[20/100] memories/...skills_layout_runtime_vs_dev.md` at 15:33.
- bundled-CLI subprocess (PID 66620) entered status `SN` (sleeping, blocked on I/O), consumed 6.94 s CPU total, never wrote to stdout again.
- Parent python (PID 43848) consumed 2.40 s CPU total over 2 h+ — idle, waiting.
- `compile.log` not modified for >1 h.
- Effect: file [20] blocked all remaining 80 files of the run.
- Eventual resolution: process was killed manually / by system reboot during operator absence; the next run resumed via state.json checkpointing.

A *crash* would have been caught (kind=unknown, retry, abort threshold). A *hang* has no detection mechanism.

## Why no timeout already

Existing crash-retry handling in compile.py (`compile_main` async-for loop + StderrCapture + log_sdk_failure) was designed for *failures*, not *hangs*. The SDK does not surface a default timeout; it inherits whatever asyncio defaults you give it (which is "wait forever" by default for an `async for` over a streaming generator).

## Fix shape

Wrap the `async for message in query(...)` in `asyncio.wait_for(..., timeout=<config>)`. On timeout: cancel the iterator, raise a synthetic failure with `kind="hang"`, classify as fatal-but-not-rate-limit, log to *-errors.log, and continue to the next file (don't abort the whole run — a hang on one file isn't a 3-strike pattern).

Sketch (compile_file body):

```python
async def _run_query(prompt, options):
    async for message in query(prompt=prompt, options=options):
        yield message

started = time.time()
try:
    agen = _run_query(prompt, options)
    while True:
        try:
            message = await asyncio.wait_for(agen.__anext__(), timeout=CONFIG.limits.compile_per_call_timeout_s)
        except StopAsyncIteration:
            break
        # ... existing message handling ...
except asyncio.TimeoutError:
    failure = log_sdk_failure(
        log, label="compile_file", source=rel_path, model=...,
        input_chars=len(source_content), started=started, capture=capture,
        exc=asyncio.TimeoutError(f"per-call timeout after {timeout}s — bundled CLI hung"),
    )
    # Ensure subprocess is terminated. SDK may not handle cancel cleanly;
    # if needed, reach into the query() internals to send SIGTERM.
    return {"_failure": failure}
```

Per-message timeout (between messages) is safer than total-call timeout: legitimate work that streams steadily for 20 min keeps going, but a 5-min silence triggers detection.

## Tunables

- `compile_per_call_timeout_s` (default proposed: 900 s = 15 min total OR 300 s = 5 min between messages — pick one model).
- Recommend the **per-message stall** model. Total-call timeout cuts off legitimate long compiles (we've seen single files at 755 s succeed); per-message timeout only triggers when the subprocess has actually gone silent.

## How to also ensure the subprocess dies on timeout

`asyncio.TimeoutError` propagating out of `async for query()` should cause the SDK to close its stdin and SIGTERM the subprocess. Verify this in the SDK source — if it doesn't, we need to reach into `transport._process` and send the signal ourselves (already accessible via the `query`'s internal state, but messy).

If the SDK doesn't clean up cleanly, fallback: spawn the SDK call inside a dedicated `subprocess.run`-style wrapper with our own process group, kill the whole group on timeout. Heavier — only do this if the simpler asyncio approach leaks zombies.

## Edge cases / risks

- **Legitimate long-running calls** (large screenshot files, big articles with curiosity gaps). Per-message stall timeout (5 min between messages) accommodates these naturally.
- **False positives during Anthropic rate-limit slow-downs**. Rate limits typically still send messages (just slower). A 5-min message-gap is way past normal rate-limit behaviour.
- **Subprocess cleanup**: zombies are a real risk if the SDK doesn't handle cancel. Test with `lsof | grep _bundled/claude` after a deliberate timeout.

## Doc updates required (when implementing)

- `scripts/wiki_config.py` — add `compile_per_call_timeout_s` to limits dataclass.
- `config.example.yaml` — document the new field.
- `KNOWLEDGE.md` — add "hang vs crash" entry alongside the existing CLI-crash one.
- Possibly `PROCESS.md` — compile section if the timeout behavior surfaces in user-visible logs.

## Cross-link

- Related: `KNOWLEDGE.md` entry on the `claude_code` preset crash (root-caused 2026-05-10). The preset-fix reduced *crash* frequency, but *hangs* are a separate failure mode that this backlog item addresses.
- Sibling: `architecture-deepening.md` — any other SDK-call site (flush.py, lint.py, query.py, scan-screenshots.py) would benefit from the same treatment. Audit them when implementing.
