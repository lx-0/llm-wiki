---
milestone: M001
project: llm-wiki
size: M
created: 2026-05-02T11:30:00Z
status: planned
total_slices: 3
completed_slices: 1
---

# M001 Roadmap

**Goal:** A new install of llm-wiki produces a working, opinionated vault setup out of the box, with engine artefacts cleanly separated from user content and known cleanup follow-ups resolved.

**Exit criteria:**

- [ ] install.sh seeds AGENTS.md / dashboard.md / .obsidian/{community-plugins,core-plugins}.json from engine templates when absent, plus skill-symlinks `<vault>/.claude/skills/* → .wiki/skills/*`.
- [ ] Engine artefacts moved: `reports/` (vault root) → `.wiki/reports/`; `.wiki/scripts/{logs,sessions,state}/` → `.wiki/{logs,sessions,state}/`. All code refs + .gitignore updated.
- [ ] Pre-compile sweep of `<vault>/Clippings/*.md` → `<vault>/raw/articles/`, with one-shot per-vault hint to reconfigure Web Clipper.
- [ ] Cleanup-followups resolved: stale `<vault>/.gitignore` patterns, Untitled.canvas, excalidraw pin re-eval, renderer-timeout configurable, wiki-config audit closed.
- [ ] Smoke test: fresh `./install.sh /tmp/test-vault-...` produces bootable vault with skills + dashboard + AGENTS template + Obsidian plugin auto-install list.

## Slices

Slice detail lives in per-slice `M001-S##-PLAN.md` files, created by `ytstack:slice-milestone`. Tentative breakdown (subject to change during slicing):

- [x] **S01 — Install seeds + skill-symlinks.** install.sh seeds AGENTS.md / dashboard.md / .obsidian/* + auto-symlinks skills. Templates land in `templates/` in the engine repo. Drives backlog items: cleanup-followups (template seeds part) + install-symlink-skills. Verified 2026-05-02 via fresh-vault smoke test.
- [ ] **S02 — Engine layout refactor + Clippings sweep.** Move `reports/` + `scripts/{logs,sessions,state}/` → `.wiki/{reports,logs,sessions,state}/`. Add pre-compile Clippings → raw/articles/ sweep. Both touch path/glob conventions and runtime gitignore — bundled to keep one consistent layout. Drives backlog items: engine-layout-cleanup + clippings-sweep.
- [ ] **S03 — Audit + minor cleanups.** Vault hygiene (stale `.gitignore` patterns, Untitled.canvas), excalidraw pin re-eval, renderer-timeout configurable, wiki-config single-source-of-truth audit close-out. Drives backlog items: cleanup-followups (remaining items) + wiki-config.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done`
