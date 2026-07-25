# Ad-hoc: Test suite wrote real vault files next to the checkout — SUMMARY

**Status: shipped 2026-07-25.** Single commit `6548069` on `main`. **Committed, NOT pushed** — verified against origin at wrapup: `main...origin/main [ahead 1]`, `origin/main` HEAD is `64bcc6e`.

**Trigger:** operator noticed a `daily/` folder sitting next to the engine checkout in `projects/lx-0/` and asked where it came from — it looked like a stray vault.

## Commits

| SHA | What |
|---|---|
| `6548069` | test: stop the suite writing real vault files next to the checkout |

## Root cause

`core/paths.py` derives everything from `__file__` under the install layout `<vault>/.wiki/`:

```
CORE_DIR = <engine>/scripts/core  →  WIKI_DIR = <engine>  →  ROOT_DIR = WIKI_DIR.parent
```

In a real install `ROOT_DIR` is the vault. In a development checkout the same line resolves to the directory **next to the repo** — so `DAILY_DIR`, `RAW_DIR`, `KNOWLEDGE_DIR` and the `_dashboard-*.md` targets point at the operator's filesystem. The collector tests monkeypatched `paths.RAW_DIR` but never `core.daily_capture.DAILY_DIR`, so the daily-rollup append ran for real.

Nothing caught it for two months because the target is outside every git repo: no `git status`, no gitignore rule, no failing assertion.

## What was found

| Location | Content | Origin |
|---|---|---|
| `lx-0/daily/` | 70 files, 23 date folders (`captures.md`, `voice.md`, `pictures.md`, `email.md`) | 22 tests, still live — newest write 2026-07-22 |
| `lx-0/daily/2025-05-15/` | `voice.md` | fixed-date fixture in `test_voice_collector.py` |
| `lx-0/knowledge/takes/` | `jane-doe.md`, `bob-smith.md` | `test_takes.py`, 2026-05-16 — no longer reproduces, files remained |
| `lx-0/_dashboard-{lint,stats}.md` | fixture stats (`articles_total: 2`) | manual `flush`/dashboard run from the repo, 2026-05-17 |
| `llm-wiki/.claude/worktrees/daily/` | 10 files | same leak one level down — worktree runs feed `.claude/worktrees/daily/` |

Leaking tests: `test_capture_collector.py` (11), `test_voice_collector.py` (5), `test_voice_collector_audio.py` (4), `test_pictures_collector.py` (1), `test_pictures_multi_inbox.py` (1).

## What landed

- `tests/_vault_isolation.py` — new. Layer 1 helper + the write guard: wraps `builtins.open` / `io.open` / `Path.open` / `Path.mkdir` / `os.{makedirs,mkdir,rename,replace,remove,unlink,rmdir}` and raises `VaultWriteEscape` on writes under `ROOT_DIR` but outside `WIKI_DIR`. Prefix comparison on `os.path.abspath` — no syscall. `rename`/`replace` guard the *destination*.
- `tests/conftest.py` — `install_write_guard()` from `pytest_configure` (undone in `pytest_unconfigure`), plus autouse `isolated_vault_paths` repointing `core.daily_capture.DAILY_DIR` at a per-test sink under pytest's tmp base. Tests that patch the constant themselves still win.
- `tests/test_vault_isolation.py` — 4 tests pinning the guard itself. Without them the patching lives only in `pytest_configure` and could stop applying unnoticed.
- `.ytstack/KNOWLEDGE.md` — incident entry (symptom → root cause → lesson → fix).
- `.ytstack/DECISIONS.md` — 2026-07-25 entry: process-level fence, not per-test patches.
- `AGENTS.md` § Path handling — the dev-checkout consequence spelled out for both tests and script runs.

## Verification

| Check | Result |
|---|---|
| Suite before fix | 1769 passed — while writing `lx-0/daily/2026-07-25/{captures,pictures,voice}.md` mid-run |
| Suite after fix | 1773 passed, 1 skipped, 14.3 s (before: 14.5 s) |
| Filesystem after run | nothing under `lx-0/` outside the checkout touched (`find -newermt`) |
| Guard negative test | `Path.write_text` on `ROOT_DIR/probe.md` raises `VaultWriteEscape`; file does not exist afterwards |
| Independent write interceptor | only the deliberate probe from the guard's own test |
| `ruff check` on the three files | clean |

Attribution came from a throwaway pytest plugin that wrapped the write entry points and recorded `PYTEST_CURRENT_TEST` per offending path — cheaper and more exact than bisecting test files, and it became the shape of the shipped guard.

## Cleanup

85 files moved (not hard-deleted) to the session scratchpad `removed-test-leak-2026-07-25/`: `lx-0/daily/`, `lx-0/knowledge/`, `lx-0/_dashboard-{lint,stats}.md`, `llm-wiki/.claude/worktrees/daily/`. `lx-0/` now contains only its 18 project folders.

## No CHANGELOG entry / no version bump

CHANGELOG is explicitly the operator-visible capability view; this is test infrastructure and changes no engine behaviour. Left at `0.3.0` deliberately. The one operator-adjacent angle — running the suite from a real `<vault>/.wiki/` install would have written junk into the live vault, and now cannot — is recorded in DECISIONS/KNOWLEDGE rather than sold as a release.

## Out-of-scope (deferred — backlog)

`.ytstack/backlog/dev-checkout-root-dir-inference.md`: only `DAILY_DIR` is proactively repointed (the others rely on the guard catching them at the write), and non-test entry points still write outside the checkout when engine scripts are run from the repo — which is how `_dashboard-*.md` got there in the first place.
