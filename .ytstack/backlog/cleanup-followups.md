---
name: Open follow-ups (surfaced during architecture review, not yet executed)
description: Cleanup + improvement candidates surfaced during the architecture review. Out of scope when surfaced; useful next time someone touches that area.
type: project
---
Surfaced during the 2026-05-01 architecture review session. None are urgent; pick up when relevant.

**Engine repo:**
- ~~`AGENTS.md` schema template missing.~~ Resolved 2026-05-02 (M001/S01): `templates/AGENTS.example.md` ships with the engine; `install.sh` seeds it into vault root when absent.
- ~~`dashboard.md` template missing.~~ Resolved 2026-05-02 (M001/S01): `templates/dashboard.md` ships; `install.sh` seeds.
- ~~`scripts/seed.py` and `scripts/sync-memories.py` `SKIP_PREFIXES` — hardcoded local FS path components.~~ Resolved 2026-05-02: replaced with `_skip_prefixes()` auto-derived from `Path.home()` + a generic workspace set; no hardcoded usernames.
- ~~`lib/config.sh:77-79` — setup-wizard text mentions "All-Inkl kasserver" by name.~~ Resolved 2026-05-02: copy generalized to "webmail-procmail provider" with All-Inkl named only as an example.

**Per-vault hygiene (applies to any installed vault):**
- **Stale `.gitignore` patterns after `.wiki/` split** — old installs may have `scripts/state.json`, `scripts/flush.log`, `scripts/session-flush-*` patterns at the vault root; those moved into `.wiki/scripts/` and are no longer needed at vault level. Each install's vault `.gitignore` should keep only `.obsidian/`, `Clippings/`, `raw/audio/*.mp3`, `.venv/`. **Status:** documented; not auto-fixed by the engine because vault `.gitignore` is per-install user content. The `vault-health-check` skill could surface stale entries on demand.
- **`<vault>/Untitled.canvas`** — empty Obsidian canvas (2 bytes, `{}`) accidentally created. Safe to delete on any install where it appears. **Status:** documented; not auto-fixed for the same reason as above.

**Tooling:**
- **Excalidraw renderer pin** — `@excalidraw/excalidraw@0.18.0` in `skills/excalidraw-diagram/references/render_template.html`. **Status:** comment added at the import site (2026-05-02, M001/S03) explaining the pin and how to re-evaluate. No version change yet — pinning stays until a sample render against the unpinned bundle is verified.
- ~~Renderer timeouts bumped hardcoded.~~ Resolved 2026-05-02 (M001/S03): `render(...)` accepts `module_timeout_ms` and `render_timeout_ms` kwargs; `render_excalidraw.py` CLI now exposes `--module-timeout` and `--render-timeout`.
