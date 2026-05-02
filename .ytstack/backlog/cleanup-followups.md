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
