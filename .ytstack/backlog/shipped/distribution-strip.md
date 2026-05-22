# Distribution-strip: keep engine-dev artifacts out of vault installs

**Captured:** 2026-05-02
**Surfaced from:** SessionEnd-hook mutation bug in lxw vault (`<vault>/.wiki/.ytstack/STATE.md` getting rewritten on every Claude Code session). Root cause split into two layers:

1. **Upstream (ytstack):** Hook mutated tracked STATE.md → fixed in [PR #17](https://github.com/Yesterday-AI/ytstack/pull/17), version 0.1.4. After merge + `/plugin update`, mutation stops.
2. **Downstream (this repo):** `install.sh` clones the full engine repo into `<vault>/.wiki/`, including `.ytstack/` (engine's dev-tracking — DECISIONS, KNOWLEDGE, milestone plans, backlog). Vaults inherit stale engine dev-state they don't need.

After the upstream fix, the leak is no longer a *bug* (no mutation). But it's still clutter — every vault carries the engine's dev history in its tree.

## Scope

`install.sh` and `wiki update` post-clone/post-pull strip:

- `.ytstack/` — engine dev-tracking, irrelevant to vault operators
- `tests/` — pytest suite, not runnable from a vault context anyway
- `.git/hooks/` — engine maintainer pre-commit hooks, may surprise vault operators
- Maybe: `docs/plans/` (legacy archived plans), `reports/` (gitignored anyway but defensive)

Keep:
- `skills/` (vault uses these — symlinked into `.claude/skills/`)
- `templates/` (seeded into vault by install.sh)
- `scripts/`, `lib/`, `hooks/` (engine runtime)
- `wiki`, `pyproject.toml`, `uv.lock` (engine entrypoint + deps)
- `README.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE` (operator-facing)

## Implementation sketch

Add a `_strip_dev_artifacts()` helper to `install.sh` (run after clone) and a similar step in `wiki update` (run after pull). Both consult a single STRIP_LIST array so the policy doesn't drift.

```bash
STRIP_LIST=(
  ".ytstack"
  "tests"
  ".git/hooks"
)
```

`wiki update` should also strip these before/after the pull, since `git pull` would resurrect anything `git`-tracked.

**Note:** since `.ytstack/` IS git-tracked in the engine repo, a plain `rm -rf` after clone doesn't survive `wiki update` unless we re-strip post-pull every time. That's the right pattern — re-strip on every update is idempotent and self-healing.

## Verification

- After `install.sh`: `find <vault>/.wiki -name .ytstack -o -name tests | head` → empty
- After `wiki update`: same check still empty
- Engine maintainer workflow unaffected: cloning the engine repo standalone (not via install.sh) keeps `.ytstack/` etc.

## Priority

LOW. Cosmetic cleanup, not a bug. Defer until after ytstack 0.1.4 lands and we have an excuse to touch `install.sh` anyway. Not blocking M003.
