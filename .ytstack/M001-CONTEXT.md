---
milestone: M001
project: llm-wiki
created: 2026-05-02T11:30:00Z
size: M
---

# M001 — Context

## Goal

A new install of llm-wiki produces a working, opinionated vault setup out of the box, with engine artefacts cleanly separated from user content and known cleanup follow-ups resolved.

## Scope

This milestone bundles five backlog items grouped under "Engine-Cleanup / DX":

1. **`cleanup-followups.md`** — AGENTS.example.md template, dashboard.md template, .obsidian seeds (community-plugins.json + core-plugins.json), vault hygiene (stale `<vault>/.gitignore` patterns, `<vault>/Untitled.canvas` removal), excalidraw 0.18.0 pin re-evaluation, renderer-timeout configurability.
2. **`engine-layout-cleanup.md`** — Move `<vault>/reports/` → `<vault>/.wiki/reports/`. Lift `<vault>/.wiki/scripts/{logs,sessions,state}/` → `<vault>/.wiki/{logs,sessions,state}/`. Update all code references and gitignore patterns.
3. **`install-symlink-skills.md`** — `install.sh` should automatically symlink `<vault>/.claude/skills/<name>/` to `<vault>/.wiki/skills/<name>/` for every skill the engine ships. Currently this is manual per install.
4. **`clippings-sweep.md`** — Pre-compile sweep of `<vault>/Clippings/*.md` into `<vault>/raw/articles/` so Obsidian Web Clipper output is visible to the pipeline. Once-per-vault hint to reconfigure the extension's default folder.
5. **`wiki-config.md`** — Audit Wiki Config single-source-of-truth status. Promote any remaining hardcoded values that should live in `CONFIG.*` and close out the backlog item.

## Exit criteria

- [ ] `install.sh` seeds `<vault>/AGENTS.md`, `<vault>/dashboard.md`, `<vault>/.obsidian/community-plugins.json`, `<vault>/.obsidian/core-plugins.json` from engine templates when absent, AND creates `<vault>/.claude/skills/<name>` symlinks for every `.wiki/skills/<name>` directory shipped with the engine.
- [ ] Engine artefacts moved out of `scripts/` and out of vault root: `reports/` → `.wiki/reports/`; `.wiki/scripts/{logs,sessions,state}/` → `.wiki/{logs,sessions,state}/`. All Python / shell / hook references updated. `.gitignore` patterns moved to match the new locations.
- [ ] Pre-compile sweep of `<vault>/Clippings/*.md` → `<vault>/raw/articles/` runs before each compile. First-run-per-vault hint emitted telling the operator to reconfigure the Web Clipper default folder. Marker file at `.wiki/state/clippings-hint-shown` (or wherever runtime state lands post-S02) prevents the hint repeating.
- [ ] Cleanup-followups items resolved: stale `<vault>/.gitignore` patterns removed (or documented as no-op for old installs), `<vault>/Untitled.canvas` removal documented, excalidraw renderer pin re-evaluated (either re-unpin or document why pinning stays), renderer timeout made configurable per-call. Wiki Config single-source-of-truth audit done — every remaining hardcoded value either promoted to `CONFIG.*` or explicitly justified as engine-internal.
- [ ] **Smoke test:** fresh clone + `./install.sh /tmp/test-vault-$(date +%s)` produces a bootable vault with skill-symlinks present, `.obsidian/` defaults seeded for community-plugin auto-install on first Obsidian launch, `dashboard.md` + `AGENTS.md` rendered from templates. Run `cd /tmp/test-vault.../.wiki && uv run python -c "import flush_pipeline; print('ok')"` and confirm green.

## Size

M — see `M001-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

(Append decisions here as they're made during slicing + execution. Format: "YYYY-MM-DD: decided X because Y.")

## Open questions

- **Clippings sweep semantics on filename collision:** skip+warn vs. timestamp-suffix? Decide during slice-milestone.
- **Vault `<vault>/.gitignore` cleanup:** the engine repo cannot edit per-install vault `.gitignore` automatically. Do we ship a one-shot migration helper, or document manual steps in `wiki update`? Decide during slice-milestone.
- **wiki-config audit scope:** is wiki-config.md fundamentally already done (config dataclasses + Personal section exist), with only minor follow-ups, or is there a deeper consolidation pending? Resolve by reading the backlog file at slice-milestone time.
