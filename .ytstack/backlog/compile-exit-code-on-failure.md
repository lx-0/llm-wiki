---
name: `wiki compile` exits 0 when every file it tried failed
description: "`wiki compile --file X` whose one file fails (auth, SDK crash) prints `1 failed` and exits 0. A caller that scripts compile (CI, a cron line, the desktop's button) cannot tell success from failure by the exit code."
type: refinement
origin: M034-S05-T06 (operator path on scratch)
created: 2026-10-16
---

# `wiki compile` exits 0 when every file it tried failed

## What happened

On the M034-S05-T06 scratch vault, the bundled Claude CLI was not logged in (sandboxed HOME).
`wiki compile --file raw/notes/operator-path-probe.md` printed:

```
ERROR  compile_file ✗ failed after 0.7s — kind=cli_crash · … result: Not logged in · Please run /login
       files:   0 done · 1 failed · 0 skipped · 0 pending of 1 candidates
```

The exit code was 0. `scripts/compile.py:main` returns nothing on every path except
"File not found" (`sys.exit(1)`).

## The decision it needs

Compile is best-effort by design: a failed file stays in the queue and the next run retries
it, and the post-passes and piggybacks run anyway. So "any file failed → exit 1" would turn
every transient SDK hiccup into a red cron line. Candidates:
- exit 1 only when files were tried and **none** succeeded (the case above);
- exit 1 when an explicit `--file` failed, keeping the batch run's 0;
- a distinct code (e.g. 3) for "partial", as `wiki dream` maps its outcomes
  (`_DREAM_EXIT_CODES`).

Check the consumers before choosing: the desktop's compile (`--progress-json`, it reads the
events), the piggyback runner, hooks that spawn compile, and the Obsidian button (Shell
commands shows a non-zero exit as a notice).
