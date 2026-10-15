---
milestone: M034
slice: S01
task: T02
project: llm-wiki
closed: 2026-10-15T19:01:00+02:00
verification: passed
---

# M034-S01-T02 -- Summary

## Commits

- `864a09d` -- M034-S01-T02 (fix): `wiki seed` handles the plugin data files in sorted order — `find` lists in directory order, which differs between filesystems, so the seed output listed dataview and extended-graph in swapped order on the CI runner (ext4) against the macOS recording (APFS); 3 of the 17 mutating goldens failed on CI for that alone (2313 passed). LC_ALL=C sort makes the order the same everywhere (the S04 port iterates sorted too); the three seed goldens moved by line order only
- `b8df503` -- M034-S01-T02: the bash oracle for the mutating commands — 17 cases recorded from the bash, each on a fresh vault and HOME with the prompt answers scripted on stdin, the golden holding the output and the change under both trees; the multi-select fix in lib/ui.sh that the recording surfaced; release 0.7.4
- `1b0cfc1` -- M034-S01-T02 (fix): config backups keep the newest snapshots when several land in one second — the backup name gained a micro-suffix only from the second same-second backup on, and `config-T-<µs>.yaml` sorts before `config-T.yaml` ('-' < '.'), so the prune-by-name deleted newer snapshots and kept the oldest
- `f390e98` -- M034-S01-T02: planned — the bash oracle for the mutating commands: each on a fresh fixture vault + HOME with scripted stdin answers (the bash prompts are line-based), the recorded effect being the change under the vault and HOME (added / changed / removed files and symlinks, small text in full, backups by pattern) plus the output: config set, setup (six wizard answers, hooks declined), hooks install user / project-all / merging into an existing settings.json, hooks uninstall, skills install / sync / --global, seed fresh / --check / --force / one path / --extract-custom, install-shortcut and --print-only

## Outcome

`tests/test_bash_oracle.py` now also records 17 mutating invocations of the bash `wiki`.
Each one gets a fresh fixture vault and a fresh HOME. Its prompt answers are scripted on
stdin: `lib/ui.sh` reads lines, and EOF takes the default. Some cases first run a setup step
whose change is not recorded. The 17 cases:

- `config set`;
- `setup` with the six wizard answers and the hooks prompt declined;
- four `hooks` cases:
  - install for claude at user scope;
  - install for all four agents at project scope;
  - install merging into a user `settings.json` that already holds another tool's hook and a
    permission;
  - uninstall after an install;
- `skills install`, `sync`, `install --global`, and `uninstall --global` after a global
  install;
- five `seed` cases: fresh, `--check` and `--force` after an edited seeded file, one path
  `--force`, and `--extract-custom` after a graph setting changed;
- `install-shortcut` and `--print-only`.

Each golden holds the command, the exit code, stdout and stderr, then a `--- change ---`
section: what was added, changed and removed under the vault and under HOME. Added small
UTF-8 files appear in full and changed ones as a unified diff. Larger or binary files appear
as size + sha256, and symlinks with their target. The engine copy's runtime parts, its
`.git` and `.wiki/logs/` are not effects.

The harness extensions in `tests/_oracle.py`:
- **`run_wiki(stdin=)`** scripts the answers.
- **`tree_manifest` / `manifest_diff`** produce the change.
- **`build_engine_template` + `install_engine`** commit the engine copy once per session and
  copy it into each fresh vault.
- **The normaliser** gained compact backup stamps (`20261015-185301[-µs]` → `<STAMP>`), which
  the revision rule had been eating.
- **`manifest_diff` compares normalised content.** A file whose only change is a timestamp
  is not an effect, which removed a flake in `seed-one-path-force`.

All 42 cases of the file run in about 56 s.

## Deviations from plan

Recording the bash before porting it found three engine defects, each fixed in its own
commit with a test watched failing first:

- **Multi-select (`lib/ui.sh` `select_many`) dropped typed choices.** The function-wide
  `IFS='|'` made "1 2 3 4" one token, so a typed selection returned nothing ("No agents
  selected"). Under bash 3.2 the empty array also died as "unbound variable" (`set -u`). It
  now splits on spaces explicitly, and an empty choice prints nothing. The
  `hooks-install-all-project` golden is its regression test. Released as 0.7.4, together
  with the next fix.
- **Config backups pruned the newest snapshots (`1b0cfc1`).** Only the second backup within
  one second got a micro-suffix, and `config-T-<µs>.yaml` sorts before `config-T.yaml`, so
  the prune-by-name kept the oldest. Every name is fixed-width now (`%Y%m%d-%H%M%S-%f`), so
  name order is time order.
- **`wiki seed` listed the plugin data files in directory order (`864a09d`).** That order
  differs between APFS and ext4, and CI failed three seed goldens on it. The `find` is
  sorted with `LC_ALL=C`.

One step the plan did not name: the engine copy is built and committed once per session
(`build_engine_template`) and copied into each case's fresh vault (`install_engine`).

## Follow-ups

- **T03:** decide open questions 1 and 2 in DECISIONS. The handlers stay `python -m`
  children behind one bootstrap hop, and the `llm_wiki` rename is dropped. Then measure
  today's process tree as the before number.
- **`update` gets its own oracle in S05,** as planned. It is the one bash-owned command not
  in this file.
- **For S02–S05:** every port is measured against these goldens. A difference is a decision
  named in the commit, never a re-recording to get green.

## Verification

Commands, both passed:
- `uv run --frozen pytest tests/test_bash_oracle.py -q`: 42 passed against the recorded
  goldens, no `--snapshot-update`. Re-run at close: 42 passed.
- `uv run --frozen pytest -q`: 2316 passed.

The guard was seen to fail. Changing `uv run python` to `uv run --quiet python` in
`lib/agents.sh`'s hook command failed all four hooks goldens on the exact line; the change
was then restored. The file was stable over four consecutive local runs. CI is green on
`864a09d` (ci + secrets-scan); the run before it, on `b8df503`, failed only on the seed order
fixed there.
