---
name: Cleanup follow-ups (deferred — not auto-fixable engine-side)
description: Items that surfaced during architecture review, were considered for M001, and were explicitly deferred because either (a) per-vault state the engine cannot touch, or (b) external-dependency state worth re-checking opportunistically.
type: project
---

> The full set of cleanup items from the 2026-05-01 architecture review was triaged into M001 (engine-cleanup). Items in this file are what's *left* — not actionable as engine-side code changes, but worth surfacing on the next pass through the relevant area.

## Per-vault hygiene (route via `vault-health-check` skill)

The engine cannot edit per-install vault content from `install.sh` or `wiki update` without surprising the operator. These belong in the `vault-health-check` skill — it reads vault state and reports findings to the operator, who decides what to act on.

- **Stale `.gitignore` patterns after the `.wiki/` split.** Old installs may have `scripts/state.json`, `scripts/flush.log`, `scripts/session-flush-*` at vault root. Those moved into `.wiki/scripts/` (and now into `.wiki/{state,logs,sessions}/` per M001/S02), so the vault-level patterns are dead. The check should surface stale entries; the operator prunes their vault `.gitignore` themselves.
- **`<vault>/Untitled.canvas`** — empty Obsidian canvas (2 bytes, `{}`) sometimes created accidentally on first vault open. Safe to delete on any install where it appears. The check can flag its presence.

## External dependencies

- **Excalidraw renderer pin** — `@excalidraw/excalidraw@0.18.0` is pinned in `skills/excalidraw-diagram/references/render_template.html` because the unpinned `?bundle` URL 404s on a transitive `@braintree/sanitize-url` dependency at the time of writing. A comment at the import site (M001/S03) describes the re-evaluation path. Re-test by replacing the pinned URL with `https://esm.sh/@excalidraw/excalidraw?bundle` and rendering a sample diagram; if it works, drop the pin. Worth a 1-minute check whenever someone is in that file anyway.

## SDK error-handling — verify in production after deployment (commit `25bcab8`, 2026-05-04)

The engine clone in the lxw vault is still on pre-fix code until the operator runs `wiki update`. Verification path after the next sync:

- **Trigger one real SDK failure** (let `compile_after_hour=18` fire, or run `wiki compile` on a known-large source). Confirm `compile-errors.log` now carries the structured diagnostic block — `kind=`, `source:`, `model:`, `input:`, `[CLI-STDERR]` lines — instead of the bare `Command failed with exit code 1` traceback.
- **Verify the rate-limit classification.** If the next abort banner reads `ABORTED (cli_crash)` (or `auth` / `network`) for fast-fail bursts, the misclassification fix landed correctly. If it still says `rate_limit` for sub-5 s failures, the stderr keyword pattern in `sdk_helpers.classify_failure` needs widening — record findings here.
- **Dashboard lock under real load.** Watch `flush-errors.log` during the next post-compile-hour window. Expected: zero `subprocess.TimeoutExpired` records; instead `dashboard refresh: another flush holds the lock — skipping (idempotent, next flush will retry)` lines in `flush.log` from contended flushes.
- **Consider a `wiki diagnose` subcommand** if classification keeps misfiring — runs `claude --version`, a one-shot `claude -p "ok"`, prints last 20 [CLI-STDERR] lines from `compile-errors.log`, surfaces auth file mtime. Pitch via office-hours if the operator hits "wait, what's actually broken" twice in a row.
