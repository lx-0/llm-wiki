---
milestone: M001
project: llm-wiki
size: M
created: 2026-05-02T11:30:00Z
status: done
total_slices: 3
completed_slices: 3
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
- [x] **S02 — Engine layout refactor + Clippings sweep.** Moved `REPORTS_DIR/STATE_DIR/LOGS_DIR/SESSIONS_DIR` from `<vault>/reports/` and `.wiki/scripts/{state,logs,sessions}/` to `.wiki/{reports,state,logs,sessions}/`. Added `scripts/clippings_sweep.py` and wired it into `compile.py`'s pre-flight. `.gitignore` updated with new patterns + legacy retained for migration window. Verified via fresh-install smoke test 2026-05-02.
- [x] **S03 — Audit + minor cleanups.** `render_excalidraw.py` timeouts made CLI-configurable (`--module-timeout`, `--render-timeout`). Excalidraw pin documented at the import site with re-eval instructions. Per-vault hygiene items (stale vault `.gitignore`, `Untitled.canvas`) deferred to the `vault-health-check` skill — not engine-side fixable. `wiki-config.md` already at `status: implemented`. All `cleanup-followups.md` items now resolved or explicitly deferred.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done`
