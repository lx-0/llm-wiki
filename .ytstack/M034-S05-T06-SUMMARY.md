---
milestone: M034
slice: S05
task: T06
project: llm-wiki
closed: 2026-10-16T04:20:00+02:00
verification: passed_with_caveats
---

# M034-S05-T06 -- Summary

## Commits

No code commit. The operator path ran on scratch and turned up no defect in the S05 head
(`a6f65d9`). The findings below are committed with this summary, along with one backlog item
and a TECH-PATTERNS lesson.

## Outcome

The operator path, end to end, on a scratch vault. The vault was installed by the real 0.7.3
installer into an iCloud-shaped path, with a sandboxed HOME and real uv behind a logging
wrapper (`/tmp/m034-scratch-operator.sh`, `…-operator-2.sh`).

| step | result |
| --- | --- |
| 0. the 0.7.3 install | exit 0, environment at `~/.venvs/scratch-wiki` |
| 1. `wiki update` (0.7.3 bash → `a6f65d9`) | exit 0; the Python phase 2 ran (two syncs, no `uv run`); a stale in-vault `.venv` was flagged with its `rm -rf` line; no hooks warning (none installed) |
| 1b. `wiki seed`, as 0.7.20's CHANGELOG asks after an update | merged Meta-Bind's buttons (2 added, 3 updated); seeded Shell commands' `data.json`, which 0.7.3 never seeded |
| 2. the desktop's spawns (its augmented PATH, no TTY, stdin closed, `env -i`) | `menu --json`, `doctor --json`, `collect --list --json`, `triage list --json`: exit 0, valid JSON. `update`: exit 0, already up to date. `query --brief --json`: exit 1, see caveat |
| 3. the Obsidian buttons (`/bin/zsh` from the vault root) | lint and refresh-stats exit 0. All 7 Meta-Bind buttons name an existing Shell commands alias. The agent buttons stopped at the SDK, see caveat |
| 4. the shortcut | `install-shortcut`, then `~/.local/bin/wiki version` from `/tmp`: exit 0, the right revision |
| 5. a fresh vault (today's installer, then `wiki setup`) | install exit 0; setup wrote claude's 3 hooks into the sandbox `settings.json`; `wiki status` shows them |
| 6. one compile | **blocked at the LLM call**, see caveat |

## Deviations from plan

- **Step 1b was added.** The plan went from the update straight to the buttons. A 0.7.3 vault
  has no Shell commands `data.json` until `wiki seed` runs, which is what 0.7.20 tells the
  operator to do after updating.
- **The stray in-vault `.venv` was traced to the 0.7.3 installer, not to today's code.**
  0.7.3 seeded before it exported the venv rule, so its dashboard step's `uv run` built
  `.wiki/.venv` inside the iCloud vault. `wiki update` reports it, as designed. Since T05 the
  installer's first `wiki` call applies the rule, so it cannot happen again; T05's
  cloud-install test pins that.

## Caveats (verification passed with these open)

- **Every LLM step stops at the Claude CLI's login.** The bundled CLI is not logged in under
  a sandboxed HOME ("Not logged in · Please run /login", 0 tokens). That covers `query`, the
  agent buttons, and step 6's `wiki compile --file`. The compile did get as far as the SDK
  call: the file selected, the model resolved (`claude-haiku-4-5-20251001`), the failure
  classified, the post-passes and the seven due piggybacks run. **The LLM round trip itself
  is unverified here.** Running it with the real HOME would write the CLI's project registry
  and transcripts into `~/.claude`. M034 did not touch compile; the operator's next real
  compile is the check. On failure the desktop shows the query's stderr, which names the
  cause.
- **`wiki compile` exits 0 when its only file failed.** That is pre-existing and a design
  question, filed as `.ytstack/backlog/compile-exit-code-on-failure.md`.

## Follow-ups

- **S05 is complete: reassess the roadmap,** then S06 (`M034-S06-PLAN.md` exists).
- **Operator, after updating lxw:**
  - `wiki seed` and an Obsidian restart, if 0.7.20's buttons never landed;
  - the stale in-vault `.venv` line from `wiki update` / `wiki doctor`, if it shows;
  - one real `wiki compile`: the LLM round trip this task could not run.
- **Lessons:**
  - TECH-PATTERNS: a sandboxed HOME has no Claude login. The context MCP was not connected,
    so TECH-PATTERNS is the fallback home.
  - KNOWLEDGE: the 0.7.3 installer's seed-before-venv order.

## Verification

- `bash /tmp/m034-scratch-operator.sh` and `bash /tmp/m034-scratch-operator-2.sh`: every
  step's exit code and payload as in the table above.
- No code changed, so no suite run beyond T05's (2656 passed, 1 skipped; CI green on
  `a6f65d9`).
