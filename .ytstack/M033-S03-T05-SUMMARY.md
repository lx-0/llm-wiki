---
milestone: M033
slice: S03
task: T05
project: llm-wiki
closed: 2026-10-15T01:12:00+02:00
verification: passed
---

# M033-S03-T05 -- Summary

## Commits

`2683f8a` — the fold (seven writers + piggyback_runner, the guard, five interleave tests).
Planning commit `b687841`. The footgun fix in `pyproject.toml` + its KNOWLEDGE entry, this
summary, the slice-plan flip and STATE follow under the same ref
(`git log --grep '^M033-S03-T05'`).

## Outcome

State through the store. Every runtime state file under `.wiki/state/` that a process
reads, mutates and writes back goes through `core.state_store.store_for(path)`: a fresh
read per run (`reload()`), every write a mutator that touches only the keys this writer
owns, applied to a fresh read under the file's sibling `.lock`, saved atomically — two
processes on one file merge key-wise instead of last-writer-wins, and a kill mid-write can
never leave a torn file. The inventory by mechanism (`.write_text(json.dumps(` on a
`STATE_DIR` file) was seven writers, not the three the audit's def-name count named:
`scan_screenshots` (`last_scan` / `total_processed`, the increment on the fresh value),
`folder_index` (one root's entry), `email_collector` (only the accounts this run scanned;
the pre-M002 shape migration stays as `_migrate_legacy`, composed by `_state()`), `flush`
(`last-flush.json`, the dedup window — parallel SessionEnd hooks are the recorded
concurrent-writer class; the stamp is taken before the locked merge, the prune happens in
place), `agent_task` (`agent-runs.json`; the facade's `sort_keys` + `trailing_newline` keep
the bytes), `dashboard/lint_results.save_cache` and `core/google_oauth._persist` (whole
payloads, not RMW → atomic `save_json_state`), plus `core/piggyback_runner.record_status`,
which was the same RMW written by hand on the seam's own primitives and now rides the facade
(same lock file, same tolerant read, same atomic save). `producers/intents.py` stays by
reason: `intents-seen.json` is a list, and the dict-only facade would change the on-disk
shape — a migration of operator state, the producer's decision.

Guards (RED first): `tests/test_state_store.py::test_state_files_are_written_through_the_seam`
— no `.write_text(json.dumps(` in a module that binds `STATE_DIR` / `STATE_FILE`, allow-list
by reason (RED on six writers, green after); and one deterministic interleave test per site
in the shape of the seam's own `test_statestore_update_rereads_fresh_and_merges` — a
concurrent writer lands a key between this run's read and its write (`find_new_screenshots`,
`write_index`, the fake reader's `scan_metadata`, `time.time`, `now_iso` as the interleave
points) and must survive the save (each RED on the old whole-dict save of the stale
snapshot). The repo-wide grep for `def _(load|save)_state(` / `_load_last_flush` /
`_load_agent_runs` is empty.

Operator-visible: nothing in behaviour. Each folded state file gains a sibling
`<name>.lock` under `.wiki/state/` (seen on the scratch vault: `folder-index.json.lock`);
`folder-index.json` keeps its shape (ASCII-escaping of a non-ASCII root id is the only
serialization difference; none exist). Smokes on the scratch vault after it pulled
`2683f8a`: `wiki index` (read + skip through the store), `wiki index --force` (write under
the lock, both roots re-written), `wiki doctor --quick`, `wiki collect --list` — all rc=0.

## Deviations from plan

- `core/google_oauth._persist` (token cache under `STATE_DIR`) was folded onto
  `save_json_state` rather than allow-listed: a whole-payload write, same bytes, and a torn
  token cache costs a re-consent — one line.
- A formatter run with an empty path variable (`ruff format $f` where `$f` came back empty
  from an rtk-filtered pipeline) formatted the whole project; ruff 0.16 formats the Python
  fences inside Markdown by default and rewrote 19 `.ytstack/**` / `CONTEXT.md` snippets
  (one into a tuple assignment) plus `docs/vault-concept.build.py`. All 32 hunks reverted by
  hand (the files are byte-identical to HEAD again); `pyproject.toml` now carries
  `extend-exclude = ["*.md"]` so Markdown is out of ruff's reach entirely (probe: a `.md` path
  answers "No Python files found"); KNOWLEDGE entry for the footgun.
- Two commits under the ref instead of one: the fold (`2683f8a`), then the footgun fix +
  closeout — the fold commit stays what the plan described.

## Follow-ups

- `producers/intents.py` seen-set: a dict-shaped `intents-seen.json` with a legacy-list
  tolerance would bring it onto the facade — the producer's decision (backlog note in the
  slice plan).
- The five collectors on `load_json_state` / `save_json_state` (jamie, health, wispr,
  calendar, gmeet) comply with the seam's contract (atomic, one writer per collector); lift
  them onto `store_for` if a second writer ever appears.
- Global TECH-PATTERNS: never pipe rtk-filtered output into a path variable; a formatter
  without an explicit path is a whole-project run.

## Verification

Plan command 1 → targeted set `104 passed`; `uv run pytest -q` → **2106 passed, 1 skipped**
(+6: the guard and five interleave tests); `ruff check` → `All checks passed!`;
`ruff format --check scripts hooks tests` → clean. Plan command 2 (the grep) → empty.
Smokes on the scratch vault as above. CI: `b687841` + `8bc4fe6` green; `2683f8a` recorded in
STATE.
