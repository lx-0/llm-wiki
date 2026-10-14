---
milestone: M033
slice: S03
task: T04
project: llm-wiki
closed: 2026-10-14T22:25:00+02:00
verification: passed
---

# M033-S03-T04 -- Summary

## Commits

`5af8c0a` — the whole fold in one commit (see Deviations). Planning commit `674dd83`. This
summary, the slice-plan flip, STATE, the KNOWLEDGE entry and the engine-layout line follow
under the same ref (`git log --grep '^M033-S03-T04'`).

## Outcome

One logging setup. `core/console.setup_console_logging(name, *, formatter, log_file,
error_file, level, silence_libraries)` is the only place the engine configures the root
logger: the 33 `logging.basicConfig` calls (20 at module level, 13 inside `main()` /
`__main__`) and the four private `_setup_logging` of the collectors / producers /
preprocessors / bridge CLIs are gone, each replaced by one seam call at the first line of
the entry function; the module-level `log = logging.getLogger(…)` stays everywhere. The
eight modules that called the seam at import (`compile`, `dream`, `flush`, `lint`, `menu`,
`query`, `preprocessors.inbox`, `preprocessors.html_ingest`) call it in `main()` now —
importing an engine module leaves the root logger untouched (17 moved modules imported in
a fresh interpreter: 0 handlers each). The ordering the `noqa: E402` comments defended
("set up the console before an import can grab root.handlers") no longer exists, so
`compile`, `menu`, `query`, `review_wiki`, `optimize_claude_md`,
`collectors/scan_screenshots` have their imports back at the top (no `noqa: E402` left in
them). The dead `__main__` blocks of `collectors/scan_youtube`, `scan_screenshots`,
`folder_index` are removed — their entry scripts carry the setup since S02. `level=` is
new: `menu_context`'s probe sets WARNING so its INFO never reaches the terminal.
`retry_failed_flushes` names `flush.log` / `flush-errors.log` explicitly: it inherited those
file handlers through flush's import-time setup before, and as a piggyback its stdio is
DEVNULL. The four CLIs keep their `logs/<name>.log` archives for the same reason.

Operator-visible: stderr of the migrated CLIs has the compile look — `HH:MM:SS` + a blank
label column for INFO (`WARNING` / `ERROR` labelled), colors on a TTY — instead of
`2026-10-14T21:59:20  INFO  …` or bare `%(message)s`; the `logs/*.log` archives keep ISO
timestamps. Smokes on the scratch vault (`/tmp/t04-smokes2.sh`, before on `4773bf2` /
after on `5af8c0a`): `wiki update`'s migration lines, `collect tabs --dry-run`,
`preprocess clippings --dry-run`, `index`, `review-wiki --dry-run --limit 1` — all rc=0,
only the prefix changed. Oracle (`menu --json`, `doctor --quick --json`, `help`)
byte-identical.

Guards (`tests/test_console.py::TestOneSetupEverywhere`, RED first): `level=` sets the
root level; no `logging.basicConfig(` under `scripts/` (RED on 33 sites, then 13, then
green); no column-0 `setup_console_logging(` under `scripts/` (RED on the eight);
importing `menu_context`, `facts.correct_apply`, `compile`, `lint`, `flush`,
`preprocessors.inbox` in a fresh interpreter adds no root handler (each RED before its
fold).

## Deviations from plan

- One commit instead of the planned A + B: the basicConfig guard is red between the halves
  (A leaves the 13 entry-local sites), and a red guard on `main` is not a state to push.
- `pyproject.toml` unchanged: its E402 ignores never named the six modules (they used
  inline `noqa`); `flush.py` (env sanitising before the SDK import) and `lint.py` (section
  imports) keep theirs for reasons unrelated to logging.
- `LOGS_DIR.mkdir` at compile's import is gone with the setup — the seam creates the log
  file's parent; every other `LOGS_DIR` writer has its own mkdir (grep).
- No migration / backfill kept a private call — the seam served every site.
- The plan's `created:` stamp and STATE's `last_updated` were an hour ahead of the clock
  (estimated, not read); corrected in this commit.

## Follow-ups

- KNOWLEDGE entry "one logging setup, called from entry points only" — the console
  docstring references it (this commit).
- M034 candidate (slice notes): `print(` vs logging.

## Verification

Plan command 1 → targeted set `50 passed`; `uv run pytest -q` → **2100 passed, 1 skipped**;
`ruff check` → `All checks passed!`; `ruff format --check` → clean. Plan command 2 (the
grep) → empty (only the docstring mention in `core/console.py`). Fresh-interpreter import of
17 moved modules → 0 root handlers each. Smokes before/after as above. CI: `4773bf2` green
(runs 38627513549 + 38627513507); `5af8c0a` recorded in STATE.
