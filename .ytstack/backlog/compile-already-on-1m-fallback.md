# Compile resilience: skip-and-flag when already-on-[1m] returns kind=unknown

## Status

Open. Original trigger of the 2026-05-15-night prompt-injection arc. Deflected at operator level (legacy stranded daily file removed). Engine-level resilience patch NOT shipped.

## Symptom

```
[1/100] [daily] daily/2026-05-15.md
  large source: 132140 chars (129.0 KB) — using claude-opus-4-7[1m] (max_turns=12)
Fatal error in message reader: Command failed with exit code 1
compile_file ✗ failed after 213.2s — kind=unknown
  model:     claude-opus-4-7[1m]
  input:     132,140 chars (129.0 KB)
  [CLI-STDERR] (empty — bundled CLI exited without writing to stderr)
```

File fails terminally. No retry. Batch counts it as a hard failure, hits `compile_max_consecutive_failures` after 3 such files in a row, aborts the whole run.

## Why the existing retry-ladder doesn't help

`scripts/compile.py:288-319` retry-on-kind=unknown logic:

```python
if (
    failure.kind == "unknown"
    and long_ctx_model
    and model != long_ctx_model         # ← guard
    and len(source_content) >= min_for_retry
):
    # retry with long_ctx_model
```

The guard `model != long_ctx_model` is false when the upfront size-gate already picked `compile_large_source_model` (1M-context Opus). No retry tier above [1m] exists. File abandoned.

## Failure-class analysis

For files ≥ 50 KB the size-gate auto-upgrades to [1m] up-front. If [1m] then returns kind=unknown after 100-500s, the cause is either:

1. **Rate-limit cascade** — Anthropic 429 caught the call, bundled CLI silently exits exit-1 / empty-stderr per its 429 behaviour. Documented in `KNOWLEDGE.md` "Compile rate-limit cascade misclassified as cli_crash".
2. **Tool-fanout context overflow even on [1m]** — wikilink-dense substrate triggers heavy Read/Grep into `knowledge/`; cumulative tool-turn context plus the 132 KB source still blows even 1M.
3. **Stream-json buffer overrun** — sdk_max_buffer_size_mb is 50 MB default, unlikely but possible on huge tool-result messages.
4. **Bundled CLI process crash** — long-running 1M-context calls have higher exposure to subprocess instability.

None of these are recoverable by retrying with the same model. Either wait (rate-limit) or split the source (overflow). Neither is something compile.py can do automatically — but **failing the file gracefully instead of terminally** is in scope.

## Proposed fix: skip-and-flag

In `compile.py` after the existing kind=unknown retry branch, add a third branch:

```python
elif (
    failure is not None
    and failure.kind == "unknown"
    and long_ctx_model
    and model == long_ctx_model
):
    log.warning(
        "  skipping file — already on long-context model %s and still "
        "failed kind=unknown; likely needs source chunking or operator "
        "review (size=%d chars, elapsed=%.1fs)",
        long_ctx_model, len(source_content), failure.elapsed,
    )
    return {"_skipped": "long_context_kind_unknown", "_failure_meta": failure}
```

The `_skipped` return shape is already handled by `main()` (line 404-408): does NOT increment `failed_count` or `consecutive_failures`. Batch continues processing other files. Failure forensics still get written via `log_sdk_failure` inside `_attempt`.

Config knob (optional): `CONFIG.limits.compile_skip_on_long_context_unknown: bool = True`. Default true (safe-by-default — batch survives). Operator can flip false if they prefer hard-fail to surface the issue.

## Test cases

- Synthesize a daily/* file > 50 KB that reliably triggers kind=unknown on [1m] (the original 2026-05-15 case is a candidate, if reproducible).
- Run `wiki compile --file daily/X.md --max-consecutive-failures 1`.
- Verify: WARNING logged, file skipped, batch continues, exit code 0 (not 1).

## References

- `.ytstack/KNOWLEDGE.md` "Compile context overflow" follow-ups
- `.ytstack/STATE.md` 2026-05-15-night arc — original trigger
- `scripts/compile.py:288-319` — existing retry-ladder where the new branch slots in
