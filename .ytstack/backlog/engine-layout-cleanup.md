---
name: Engine layout cleanup — move reports/ + runtime dirs out of vault/scripts
description: Two vault-layout requests. (1) Move reports/ from vault root into .wiki/reports/ — they're engine output, not user content. (2) Move .wiki/scripts/{logs,sessions,state}/ up to .wiki/{logs,sessions,state}/ — runtime artefacts shouldn't live inside the scripts/ code folder.
type: refactor
origin: vault-observation
created: 2026-05-02
---

# Engine Layout Cleanup

Two related path moves. Both are pure reorganization — no behavioral change beyond where artefacts land on disk.

## (1) `reports/` — out of vault root, into `.wiki/reports/`

**Today:** `<vault>/reports/wiki-review-YYYY-MM-DD.{md,json}` is written at vault root.

**Problem:** A vault-root folder reads to the user (and any agent skimming the vault) as **user content**. `reports/` is *engine output* — review-wiki.py and lint.py write here, the user only consumes occasionally. Belonging at the root inflates the user-visible surface and clutters the Obsidian file-tree.

**Move to:** `.wiki/reports/`

**Touchpoints:**

- `scripts/config.py:37` — `REPORTS_DIR = ROOT_DIR / "reports"` → `WIKI_DIR / "reports"` (or wherever `.wiki/` is rooted in config)
- `scripts/config.py:15` — comment "vault-root, user-visible" needs updating
- `scripts/review-wiki.py`, `scripts/lint.py` — pick up via `REPORTS_DIR`, no direct path strings expected (verify with grep)
- `<vault>/.gitignore` — drop the `reports/` line; add equivalent under `.wiki/.gitignore` if needed (probably not — reports might want to be git-tracked inside the engine repo so users have a history)
- Existing reports: `wiki-review-2026-04-13.{md,json}`, `wiki-review-2026-04-14.{md,json}`, `wiki-review-2026-04-23.{md,json}` — `git mv` to preserve history.

## (2) `scripts/{logs,sessions,state}/` — out of scripts/, up to `.wiki/`

**Today:**

- `.wiki/scripts/logs/flush.log` (~478 KB)
- `.wiki/scripts/sessions/` (transient pre-compact context dumps)
- `.wiki/scripts/state/{state,piggyback-state,email-state,screenshot-state,last-flush}.json`

**Problem:** Runtime artefacts (logs, transient session files, state JSON) sit inside the **code folder**. Mixing code and data violates the same instinct as #1 — `scripts/` should be readable as "the engine source", and runtime spillage clutters that. Also makes `.gitignore` patterns more entangled than they need to be.

**Move to:**

- `.wiki/logs/`
- `.wiki/sessions/`
- `.wiki/state/`

**Touchpoints:**

- `scripts/flush.py` — `STATE_DIR = SCRIPTS_DIR / "state"` and similar constants for `logs/`, `sessions/`. Update to `WIKI_DIR / "..."`.
- `scripts/compile.py`, `scripts/scan-screenshots.py`, `scripts/retry-failed-flushes.py`, `hooks/pre-compact.py` — anything reading state files. Run a grep for `state/`, `sessions/`, `logs/` literals.
- `.wiki/.gitignore` (or wherever the runtime gitignore lives) — patterns for `logs/`, `sessions/`, `state/*.json` minus a kept-in-VCS allowlist.
- Existing files: `git mv` to preserve history.

## Why bundle these two

Same theme: separating **user-content** / **engine-code** / **engine-runtime**. Three distinct categories, each with its own folder. After both moves the vault has a cleaner mental model:

```text
<vault>/
├── daily/                   ← user content (auto-collected)
├── knowledge/               ← user content (compiled wiki)
├── raw/                     ← user content (sources)
├── inbox/, Clippings/       ← user content (incoming)
├── AGENTS.md, dashboard.md  ← user content (config)
├── .obsidian/               ← Obsidian config
└── .wiki/                   ← engine, fully self-contained
    ├── scripts/             ← engine code
    ├── prompts/, lib/, …    ← engine code
    ├── reports/             ← engine output (NEW location)
    ├── logs/                ← engine runtime (NEW location)
    ├── sessions/            ← engine runtime (NEW location)
    ├── state/               ← engine runtime (NEW location)
    ├── config.yaml          ← engine config
    ├── .ytstack/            ← engine planning
    └── .git, .venv          ← repo + deps
```

## Edge cases

- **Existing installs.** If the engine is shared across machines (it is — Sync.app), all clones must run the migration. Probably a one-shot `scripts/migrate-layout.py` that detects old paths and `git mv`s them in-place, idempotent.
- **`.gitignore` discipline.** `state/*.json` should stay tracked for diff-able pipeline state (visible in commit history); `logs/*.log` and `sessions/flush-context-*` should stay ignored. Verify the new locations carry the same rules.
- **Backwards compat?** None needed — the engine reads its own paths, no external consumers.

## Source

Surfaced 2026-05-02 during a vault-status review. The intent: move `reports/` from the vault root into `.wiki/reports/` (it's engine output, not wiki content), and lift the engine runtime folders `.wiki/scripts/{logs,sessions,state}/` up to `.wiki/{logs,sessions,state}/` so the engine layer is flat under `.wiki/` rather than nested inside `scripts/`.
