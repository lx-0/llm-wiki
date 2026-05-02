---
name: Open follow-ups (surfaced during architecture review, not yet executed)
description: Cleanup + improvement candidates surfaced during the architecture review. Out of scope when surfaced; useful next time someone touches that area.
type: project
---
Surfaced during the 2026-05-01 architecture review session. None are urgent; pick up when relevant.

**Engine repo:**
- **`AGENTS.md` schema template missing** — the vault's `AGENTS.md` (article-schema spec embedded into every compile prompt) has no template counterpart in the engine. New installs have no starting point. Candidate: `docs/AGENTS.example.md` + `install.sh` seeds it into the vault root if absent. Same pattern as `config.example.yaml`.
- **`dashboard.md` template missing** — every install would benefit from the user's Obsidian Dataview dashboard. Candidate: `templates/dashboard.md` + `install.sh` seed.
- ~~`scripts/seed.py` and `scripts/sync-memories.py` `SKIP_PREFIXES` — hardcoded local FS path components.~~ Resolved 2026-05-02: replaced with `_skip_prefixes()` auto-derived from `Path.home()` + a generic workspace set; no hardcoded usernames.
- ~~`lib/config.sh:77-79` — setup-wizard text mentions "All-Inkl kasserver" by name.~~ Resolved 2026-05-02: copy generalized to "webmail-procmail provider" with All-Inkl named only as an example.

**Per-vault hygiene (applies to any installed vault):**
- **Stale `.gitignore` patterns after `.wiki/` split** — old installs may have `scripts/state.json`, `scripts/flush.log`, `scripts/session-flush-*` patterns at the vault root; those moved into `.wiki/scripts/` and are no longer needed at vault level. Each install's vault `.gitignore` should keep only `.obsidian/`, `Clippings/`, `raw/audio/*.mp3`, `.venv/`.
- **`<vault>/Untitled.canvas`** — empty Obsidian canvas (2 bytes, `{}`) accidentally created. Safe to delete on any install where it appears.

**Tooling:**
- **Excalidraw renderer** — pinned `@excalidraw/excalidraw@0.18.0` in `skills/excalidraw-diagram/references/render_template.html` because the unpinned `?bundle` had a 404 on a transitive `@braintree/sanitize-url` dep. Watch for upstream fix; can re-unpin if 0.18+ becomes the default.
- **Renderer timeout bumped** to 90s/60s in `render_excalidraw.py` for the 181-element architecture diagram. May want to make this configurable per-call.
