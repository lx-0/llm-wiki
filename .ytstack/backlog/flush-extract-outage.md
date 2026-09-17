# Backlog: flush-extract outage — cli_crash class + diverging retry queue

Found by the 2026-08-25 full-state audit (reviews/2026-08-25-lxw-vault-audit.md).
Severity: HIGHEST operative defect — Path A (session capture → daily/) is dead.

## Symptom

Since ~2026-08-14 `flush_extract` fails ~99%: bundled CLI exits 1 with empty
stderr after 4–6 s, kind=cli_crash (152×/30 d) + kind=unknown (13×). Inputs are
consistently 57–87 KB — the known-fragile size class (compile logs its own
"entering known-fragile size class" warning at 67 KB). `daily/<d>/sessions.md`
last written 2026-08-05. Retry queue `sessions/failed-flushes/`: 234 contexts
(~17 MB), oldest 2026-07-20; inflow ~5/day, drain 5 per COMPILE day (2 compile
days in 30) → never converges.

## Leads (do NOT assume — Memory: same surface, 3 distinct root causes)

1. `flush_extract` pins NO model (`sdk_helpers.py:753` → "(default)") — every
   other SDK path pins one. Bundled-CLI default-model behavior may have changed.
2. Size class 57–87 KB: the 1 MB stream-json buffer / 200K-context classes were
   distinct historic causes — classify via stderr capture + timing first
   (systematic-debugging, not pattern-match).
3. Two `Control request timeout: initialize` on 2026-08-14 — the day it started.

## Fix shape (after root cause)

- Root-cause the crash class; add model pin if that is the cause.
- Retry drain: decouple from compile cadence (own piggyback cooldown or drain-N
  proportional to queue depth); 234-deep queue needs a catch-up mode.
- Regression: flush E2E over a 70 KB fixture.

## 2026-09-17 addendum — a fourth cause, and the drain is the open item

The exit-1-empty-stderr signature recurred 2026-09-09→17 with a **fourth** root
cause: the API's client-version floor (`claude_code_version_too_old`, bundled CLI
2.1.97 < 2.1.251). Fixed in 0.5.3 (SDK 0.2.153, `cli_outdated` kind, flush via
`run_sdk_query`, `flush-pipeline` doctor check) — KNOWLEDGE 2026-09-17 has the
full trace. The regression assertion this item asked for exists:
`tests/test_sdk_mcp_isolation.py` (harness isolation + "flush must not bypass").

What is still open is the **drain**, and it is now the expensive part:

- 445 archived contexts after the fix; **361 are re-captures of the same three
  long-lived Codex threads** (Stop fires per turn, every fire archived its own
  copy). `retry-failed-flushes.py` retries oldest-first, 5 per run, and each
  success `append_to_daily` REPLACES the same per-session block — so ~360 SDK
  calls would produce three blocks.
- The retry only fires from a *successful evening flush* (piggyback) or a
  compile. During the outage neither happened, so the queue never drained and
  compile did not run for eight days either.

Fix shape: (1) collapse the archive to the newest context per `session_id`
before draining (older copies are strictly superseded by replace-in-place
semantics — the same thing the live path does every turn); (2) drain on its
own cadence, proportional to queue depth, not gated on flush success;
(3) keep `flush-pipeline` as the watchdog. (1) is an hour; it turns a
months-long drain of 445 into ~60 calls.
