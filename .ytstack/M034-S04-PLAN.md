---
milestone: M034
slice: S04
project: llm-wiki
created: 2026-10-15T18:15:32+02:00
status: planned
task_count: 5
completed_tasks: 2
---

# M034-S04 -- Slice Plan

**Goal:** `wiki seed` runs in Python, with every template merge at parity on the fixture vault
and on a copy of the live `.obsidian/`; `lib/seed.sh` (708 lines) is deleted.

Re-cut before T01 with what S03 taught (see Notes). The planning reading found a constraint
the first cut missed: **install.sh sources lib/seed.sh** and seeds before its `uv sync`.
Deleting the library means the installer seeds through `wiki seed` after the venv exists.

## Tasks

- [x] T01 -- **Oracle first, fix first.** Record the bash on the branches the six seed cases
  miss:
  - the special merges over existing operator data (community plugins, `appearance.json`,
    meta-bind by id, the agent shell commands by id, the `.env` example's per-var append);
  - a seed / `--check` / `--force` with an overlay in `.wiki/custom/`;
  - a targeted path that matches nothing;
  - `--check` together with `--force`;
  - `--extract-custom` with no drift;
  - a merge target that is not JSON.

  Bash defects the recording turns up are fixed in the bash first, then recorded (a
  release when operator-visible). Open question 4 is decided in DECISIONS: port the jq
  merges to Python `json`, held to the bash by recorded goldens.
- [x] T02 -- **The seed core, pure:**
  - the template walk and its skip rules;
  - semantic file equivalence (what `jq -S` gave);
  - the overlay: apply (element-wise deep merge, arrays by index), compute (leaf paths),
    extract.

  Byte parity with the bash. The bash's outputs are recorded as goldens and pushed before
  T05 deletes it (S03-T07's pattern).
- [ ] T03 -- **The special merges, pure** (as T01's fixes left them, 0.7.20 / 0.7.21):
  - the list union for community plugins and `appearance.json`'s snippets
    (`_merge_list_union`: writes only when it adds; jq `unique` on a merge);
  - the two button registries by id, in place (`_merge_registry`: Meta-Bind's
    `buttonTemplates`, Shell commands' `shell_commands`, the legacy object form), with
    `dashboard.agent_buttons` in-process (no `uv run`);
  - the `.env` example's stanza append;
  - the dashboard agent-button rewrite.

  Each is at parity on the fixture and on a copy of the live vault's `.obsidian/` (arrays
  included; read-only source, copied to a tmp dir), recorded the same way.
- [ ] T04 -- **The `seed` command** in Python:
  - `--force`, `--check`, a targeted `<path>`, `--extract-custom`;
  - the help;
  - the dashboards refresh after a writing run.

  All seed goldens pass, and `test_seed_preserves_caches.py` stays green. The `--check`
  report uses the engine-relevant subset if the port makes that cheap
  (`backlog/seed-semantic-diff.md`).
- [ ] T05 -- **The installer and the deletion.** `install.sh` seeds through `./.wiki/wiki
  seed` (`--force` on the operator's overwrite choice) after its venv sync. Then
  `lib/seed.sh` and `require_cmd jq` go: seed was jq's last user. The docs follow. A
  scratch `install.sh` into a fresh vault, plus `wiki seed` and `--force` on a copy of the
  live `.obsidian/`, match the goldens.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`; no bash left for seeding.

## Notes

The memory "round-trip on the real data shape before a live `--force`" applies: the live
vault's `.obsidian/` JSON carries arrays and plugin data the fixture may not. Copy it and
compare; never write the live vault. T01 proved it: only the copy of lxw's `.obsidian/`
showed the plugin's own migrations (renamed icons, added `debounce`) that a replacing merge
would undo on every seed. The run's shape: `tests/_oracle.py` builds an engine copy and a
fixture vault in a tmp dir, the live `.obsidian/` and `dashboard.md` are copied in, then
`seed --check`, `seed`, `seed --check`, and a diff of each merged file.

**What S03 taught for this slice** (reassessment after S03, outcome A: the slice order
holds; these refine the tasks when they are planned):
- **Expect the task count to grow.** Each S03 port needed:
  - oracle-first recording of the branches the existing goldens miss (S01 has six seed
    cases);
  - fix-first for the bash defects that recording turns up;
  - a pure merge layer held to the bash, and the bash's output recorded as goldens and
    pushed before the delete (S03-T07's pattern, `tests/golden/agents/`).

  S03 went from 4 tasks to 7. Split early rather than overflow a task.
- **Python resolves paths; the bash used the path `wiki` was started through.** Anything
  seed writes or compares as an absolute path (shell-command configs, button commands, the
  overlay's paths) is checked for a vault reached through a symlink. Compare resolved, and
  state what changes (S03-T06, CHANGELOG 0.7.18 / 0.7.19).
- **`require_cmd jq` in `wiki` is there for seed alone.** It goes with `lib/seed.sh` in this
  slice's last task, and the bootstrap no longer needs jq.
- **Byte parity traps** (KNOWLEDGE, S03-T05): bash's `printf %-Ns` pads by bytes, prompts
  must flush stdout first, and a golden must not hold a machine-dependent number.
