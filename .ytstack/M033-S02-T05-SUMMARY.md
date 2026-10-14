---
milestone: M033
slice: S02
task: T05
project: llm-wiki
closed: 2026-10-14T20:58:00+02:00
verification: passed
---

# M033-S02-T05 -- Summary

## Commits

`b96865a` — the code, tests and docs; this summary, the slice-plan flip and STATE follow in
the next commit under the same ref (`git log --grep '^M033-S02-T05'`). Planning commit
`856c6d2`.

## Outcome

Both operator paths run end to end from the engine as pushed, on scratch copies only (the live
lxw vault was read — HEAD, remote, `config.yaml` — never touched).

**Update path.** A scratch clone pinned to the lxw checkout's `5b6b947` (2026-10-12, origin =
this repo via `file://`, the operator's `config.yaml` copied in) fast-forwarded through the
whole M032 / M033 arc (565 files), synced its venv, migrated and synced skills — and exposed
the one defect the layout change has for an operator: the bash that starts `wiki update` is
parsed before the pull, so its post-pull steps ran the OLD spawn shape against the NEW tree
(`migrations/migrate_config_keys.py` by file path → `ModuleNotFoundError: core`, warned,
migration skipped; the second update healed it). `cmd_update` now ends its first phase in
`exec "$WIKI_DIR/wiki" update --post-pull <rev>`; `_update_post_pull` (uv sync, both
migrations as `-m` modules, skills sync) runs from the pulled tree. Traced on the scratch
engine with real uv: `+ exec /tmp/lxw-scratch/.wiki/wiki update --post-pull b96865a`, then
phase two from the new process ("Already up to date", sync, "already on the current key
schema", skills).

**Fresh-install path.** `install.sh` from the local repo into an empty target: sparse-checkout
(`.ytstack` + `tests` absent), seeding (keep-existing, non-TTY), skills symlink, venv at
`.wiki/.venv`; a `wiki update` on it afterwards, clean.

**Entry points on the updated scratch** — all rc 0, no `RuntimeWarning` / `Traceback` /
`ModuleNotFoundError`: `version`, `help`, `doctor --quick --json`, `collect --list`,
`preprocess --list`, `config get models.compile_model`, `process-inbox --help`,
`ingest-html --help`, `review-wiki --dry-run`, `ingest-youtube --help`, `index --help`; the
three hooks exactly as `lib/agents.sh:hook_cmd` installs them (`cd '<wiki>' && uv run python
hooks/<name>.py`, `{}` on stdin — session-start prints its block, session-end / pre-compact
log "No transcript_path … exiting"); `-m core.piggyback_runner --help`, `-m lint --help`, and
the four bash-spawned modules from T03.

**Second defect, found because `--help` smokes lie.** cli.py answers `--help` from the
CommandSpec's `help_text`, so the handler is never spawned; every real `wiki ingest-youtube …`
and `wiki index …` had printed runpy's `RuntimeWarning` on every run since T03's `-m` spawn
(`collectors/__init__` already imports both modules — double import, double registration).
Both enter through top-level modules now (`scripts/ingest_youtube.py`,
`scripts/index_folders.py`, each keeping its module's local logging setup); `folder_index`'s
`if __package__` guard — dead since the bootstrap went (`core.paths` is imported above it, a
by-path run cannot start) — is removed and the adapter registers like every other collector.

**Guards.** `tests/test_wiki_update.py` (real git + the real bash layer, `uv` a logging stub):
the pulled stub `wiki` must print the hand-off marker with `--post-pull <rev> --no-skills`;
phase two on its own spawns `uv sync` and both migrations as `-m` modules with `scripts/` on
PYTHONPATH. `tests/test_cli_dispatch.py`: the four entry modules run once without the runpy
warning; no handler may live in a package whose `__init__` imports it (lists offenders by
command).

**Docs.** `docs/engine-layout.md` tree reconciled with the 165-file inventory (`calendar.py` →
`calendar_collector.py`, ~60 missing entries added, `migrations/` listed in full, `core/`
complete) plus "How a module runs"; `AGENTS.md` carries a directory-level map — the
file-by-file reference lives in engine-layout, two per-file trees had drifted 70 and 85
entries apart — and the three invocation forms with the sub-package rule. Oracle unchanged
(`tests/test_oracle_payloads.py` green in the suite).

## Deviations from plan

- Two engine fixes the proof uncovered (the plan allowed for them): the `wiki update` phase
  split, and the two entry modules + guard removal. Both TDD'd — RED seen (marker absent with
  the old bash's own post-pull output; `--post-pull` unknown; `No module named
  ingest_youtube` / `index_folders`; the guard listing exactly `index` and `ingest-youtube`).
- `AGENTS.md`'s tree became a directory-level map instead of a second per-file tree (see
  Docs above).
- `wiki index` now pays the `import collectors` cost the dead guard once avoided: ~0.25 s on
  the dev Mac (measured), accepted.
- The lxw vault itself was not updated (scratch only, by design). Its first `wiki update`
  still runs the pre-fix bash: two warnings (config + log migration spawned by path), then
  `wiki update` once more; lxw's config needed no migration anyway ("already on the current
  key schema").
- `gh run list --commit <short-sha>` found nothing for 100 s while two runs were already
  green — the full SHA or a prefix match on `--json headSha` (KNOWLEDGE).

## Follow-ups

- T06 (added while planning T05): the ~60 documented by-path invocations of sub-package
  modules in `docs/PROCESS.md`, `docs/FEATURES.md`, `docs/config.md`, 13 docstrings and the
  `config_docs` hint strings; includes a decision for the direct-CLI flags of
  `scan_screenshots` / `scan_browser` / `scan_tabs`, which have no warning-free entry yet.
- Operator note for lxw (in STATE): first `wiki update` across this change warns twice — run
  it twice.
- S03 candidate: lazy collector registration (`import collectors` on every `wiki index` /
  `wiki collect`).

## Verification

Plan commands: `/tmp/lxw-scratch/.wiki/wiki update && … doctor --quick --json && … collect
--list && LLM_WIKI_REPO=file://$PWD/.git ./install.sh /tmp/lxw-fresh && /tmp/lxw-fresh/.wiki/wiki
doctor --quick` → all rc 0 (logs `/tmp/lxw-scratch-update.log`, `/tmp/lxw-scratch-probes.log`,
`/tmp/lxw-fresh-install.log`); `uv run pytest tests/test_oracle_payloads.py tests/test_layout.py
-q` → green; `uv run pytest -q` → **2053 passed, 1 skipped**; `ruff check` → `All checks
passed!`; `ruff format --check` → 388 files; `bash -n wiki lib/*.sh` → ok. Exec hand-off on the
real engine: scratch at `856c6d2` → `wiki update` → `b96865a` (old bash, clean because T03's
`-m` shape was already in place) → second `wiki update` under `bash -x` → `+ exec …/wiki
update --post-pull b96865a` → phase two output from the new process. CI on `origin/main` after
the push: recorded in STATE.
