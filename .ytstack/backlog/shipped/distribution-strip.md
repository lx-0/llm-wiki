# Distribution-strip: keep engine-dev artifacts out of vault installs

**SHIPPED 2026-05-22** (commit on `install.sh`). Implemented via git **sparse-checkout**, not the `rm -rf` sketch below — see "What actually shipped".

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

## What actually shipped (2026-05-22)

The `rm -rf` sketch above is **broken** for this repo's update path: `.ytstack/` + `tests/` are git-tracked, and `wiki update` runs `git pull --ff-only`. A working-tree deletion of tracked files makes the next pull abort (`Your local changes would be overwritten`) the moment those paths change upstream — which `.ytstack/` does every milestone. The "self-healing re-strip" idea would have bricked `wiki update`.

Shipped instead: **git sparse-checkout** in `install.sh`, right after the clone:

```bash
STRIP_LIST=( ".ytstack" "tests" )
sparse_patterns=( '/*' )
for p in "${STRIP_LIST[@]}"; do sparse_patterns+=( "!/$p/" ); done
git -C "$DEST" sparse-checkout set --no-cone "${sparse_patterns[@]}"
```

Why this is correct: the paths stay **tracked** (so `git pull --ff-only` never sees a dirty tree) but are omitted from the **checkout**. The setting persists in `.git/info/sparse-checkout` + `core.sparseCheckout=true`, so **every future `wiki update` honours it automatically** — no update-side change needed (the doc's biggest worry evaporates). `.git/hooks` dropped from scope: a `git clone` only carries `*.sample` hooks, never the maintainer's active local hooks, so there's nothing to strip.

**Verified** (isolated /tmp clone + full edited-`install.sh` run): strip applied, `git pull --ff-only` survives an upstream `.ytstack/` change with the strip intact, kept paths update normally, sparse config persists.

**Existing installs are not auto-stripped** (sparse-checkout only configured for new clones). To strip an already-installed vault once (safe when `git -C <vault>/.wiki status` is clean):

```bash
git -C "<vault>/.wiki" sparse-checkout set --no-cone '/*' '!/.ytstack/' '!/tests/'
```

lxw still carries `.wiki/.ytstack` + `.wiki/tests` (installed pre-change); operator can run the one-liner above when convenient.

## Priority

~~LOW~~ — DONE.
