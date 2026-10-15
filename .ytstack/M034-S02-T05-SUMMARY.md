---
milestone: M034
slice: S02
task: T05
project: llm-wiki
closed: 2026-10-15T21:42:00+02:00
verification: passed
---

# M034-S02-T05 -- Summary

## Commits

- `fa23801` -- M034-S02-T05: S02 closes — the docs name what the bash still owns, install.sh's next steps say six questions (0.7.14), and the operator path runs end to end on a fresh vault

## Outcome

**The deletions this task planned had already happened** with each port (T02–T04), as "no
soft deprecation" requires: `cmd_config`, `cmd_setup`, `cmd_install_shortcut`, the wizard and
its validators, `config_keys` / `config_path` / `config_cmd_*`, `lib/ui.sh`'s `ask` /
`pause`. This task did the rest.

- **Docs pass.** CONTEXT.md now covers:
  - the dispatch kinds incl. `alias`;
  - the one hop;
  - the bash owning only hooks / skills / seed / update / status;
  - bare `wiki` decided in `cli.py`.

  AGENTS.md describes `lib/` as it shrinks and names `core/console`'s status helpers.
  `install.sh`'s next steps say six questions (0.7.14).
- **The operator path, end to end, on a fresh vault:**
  1. `install.sh` from the local repo (`LLM_WIKI_REPO=file://…`);
  2. the first `wiki` call with the real HOME (the first sync + stamp);
  3. `wiki setup` in a sandboxed HOME, with six defaults and `y` to hooks. The bash
     installer's answers came on the same stdin, and it wrote claude's three hooks
     (SessionStart / SessionEnd / PreCompact) into the sandbox `~/.claude/settings.json`;
  4. `wiki status` shows claude installed.

## Deviations from plan

- **The first end-to-end attempt failed on the environment, not the product.** `jq` resolved
  to asdf's shim, which cannot run under a foreign HOME (exit 126, no output); it was rerun
  with `/usr/bin` first. Lesson in TECH-PATTERNS: a sandboxed HOME breaks every asdf tool
  silently.
- **That failure exposed a real bash defect, now in S03-T02's plan.** When a hook payload
  cannot be built, the installer reports `✗ unknown agent: claude`, writes nothing, and
  still ends `✓ Done. Restart agent CLIs…` with exit 0. Fix it in the bash first, then
  record it, then port.

## Follow-ups

- **`reassess-roadmap` for S02.**
- **S05-T04** (install.sh re-checked): `install.sh` could write the venv's `.wiki-synced`
  stamp after its own successful `uv sync`, so the first `wiki` call does not sync again.

## Verification

- **The end-to-end run.** Every step exits 0, the sandbox HOME holds the hooks, and status
  shows them.
- **The grep pass.** No stale reference left in README / AGENTS / CONTEXT / docs / install.sh.
- **The suite.** `uv run --frozen pytest -q`: 2428 passed, 1 skipped.

CI is green on `fa23801` (ci + secrets-scan).
