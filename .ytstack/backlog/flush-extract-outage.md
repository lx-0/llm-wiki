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
