---
milestone: M034
slice: S01
task: T01
project: llm-wiki
closed: 2026-10-15T18:28:41+02:00
verification: passed
---

# M034-S01-T01 -- Summary

## Commits

- `dcfeebb` -- M034-S01-T01 (fix): the bash oracle's doctor golden held two machine values — the CI runner (Ubuntu, bash 5) matched 24 of the 25 macOS-recorded goldens byte for byte; engine_revision and the eviction check's file count are normalised now
- `e574a13` -- M034-S01-T01: the bash oracle for the read-only commands — 25 invocations of the real `wiki` recorded from the bash before any port
- `4765232` -- M034-S01-T01: planned — the bash oracle for the read-only commands

## Outcome

`tests/test_bash_oracle.py` runs the real bash `wiki` out of an engine copy in the M033
fixture vault and compares 25 read-only invocations against `tests/golden/bash/*.txt`. Each
golden holds the command, the exit code, stdout and stderr, all normalised. The 25 cover:

- `help` and the bare entry without a TTY;
- the eleven bash-owned help texts;
- `version`, `status`, `menu` (no TTY and `--json`), `doctor --quick --json`;
- `config get/keys/path/status` and an unknown subcommand;
- `hooks status`, `skills status`.

The harness lives in `tests/_oracle.py`, extended rather than forked:
- **`build_engine_copy`** copies the runtime parts, not symlinks, because `core/paths`
  resolves its own file. It commits them once with a fixed author, date and origin, so
  `wiki version` reports a checkout.
- **`write_uv_shim`** puts a `uv` on PATH that execs the test venv's python. No environment
  is synced or mutated, and the bash still makes its own hop.
- **`run_wiki`** runs with no TTY, a scratch HOME and PATH = shim + `/usr/bin` + `/bin`.
- **`normalise_text`** replaces paths, revisions, timestamps and ages; the golden comparers
  take a `golden_dir`.

The fixture points Ollama at a closed local port. Run time is about 4 s. The cases are
order-independent, and the same goldens hold on macOS (bash 3.2) and the Ubuntu runner
(bash 5).

## Deviations from plan

- **`prompts/` was missing from the engine copy.** The first copy lacked it, and since
  79eb961 `scan_screenshots` reads its prompt at import, so the first doctor golden froze a
  "Prompt file not found". The copy now includes `prompts/`, and every golden was read for
  environment errors before commit.
- **The doctor golden needed one fix after CI.** CI failed on that golden alone: the engine
  copy's commit hash and the eviction check's file count are machine values. JSON payloads
  now get the text normalisation before parsing, and one named machine-count key is
  blanked.
- **Two later plan lines were corrected.** While reading the bash for T02 I found two lines
  in the S02 plan that did not match the code. The prompt helpers must be line-based like
  `lib/ui.sh` (piped answers are read, EOF takes the default), not refuse without a TTY.
  `install-shortcut` prints the rc line and never edits an rc file.

## Follow-ups

T02 records the mutating commands into the oracle:
- `config set`, `hooks install/uninstall`, `skills install/uninstall/sync`;
- `seed` in its modes, `install-shortcut`, `setup`.

Each runs on a fresh fixture and HOME, with answers scripted on stdin. The recorded effect is
a manifest of every file and symlink under the vault and HOME.

## Verification

Commands: `uv run --frozen pytest tests/test_bash_oracle.py -q` (25 passed, recorded goldens,
no `--snapshot-update`) and `uv run --frozen pytest -q` (2298 passed) — passed. The guard was
seen to fail: one word changed in `wiki hooks --help` gave the exact line diff, then was
restored. CI green on `dcfeebb` (both jobs).
