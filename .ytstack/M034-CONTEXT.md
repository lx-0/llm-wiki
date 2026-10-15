---
milestone: M034
project: llm-wiki
created: 2026-10-15T18:13:20+02:00
size: L
---

# M034 -- Context (Dispatcher + surface diet)

The third and last milestone of the de-slop arc (`backlog/deslop-arc.md` §6). M032 rebuilt the
desktop, M033 modernised the Python. M034 moves the bash command layer into the Python
dispatcher and cuts the operator-facing surfaces (help, menu, README, AGENTS) to what their
readers use.

## Goal

`wiki` is a thin bash bootstrap that hands every command, in one hop, to one Python dispatcher.
One command table sits behind both `wiki help` and the home menu, and the README, AGENTS.md and
the TUI carry only what their readers use.

## Measured starting point (2026-10-15)

- **Bash: 2,885 lines.** `wiki` 852 + `lib/*.sh` 1,827 + `install.sh` 206.
  - Bash still owns 14 commands. By size: `update` 120 + `_update_post_pull` 69,
    `seed` 89 + `lib/seed.sh` 708 (jq JSON merges, overlays, plugin and env merges),
    `install-shortcut` 72, `skills` 36 + `lib/skills.sh` 322, `hooks` 10 + `lib/hooks.sh` 138
    + `lib/agents.sh` 255 (writes agent configs under `~`), `config` / `setup` 14 + 14 +
    `lib/config.sh` 199 + `lib/ui.sh` 100 (the interactive wizard), `dream` 36,
    `dream-entity` 26, `version` 30, `menu` 29, `doctor` 30, `status` 7.
  - Bash also carries four bash help texts (`help_config` / `hooks` / `setup` / `skills`,
    117 lines) next to Python's `cli_help.py`, and `lib/common.sh` (105, venv resolution
    incl. the iCloud `~/.venvs/<vault>-wiki` rule).
- **Three processes per Python command.** `wiki` execs `uv run --project .wiki python
  scripts/cli.py`, and `uv` stays as the parent of the dispatcher. `cli.py` then runs every
  handler as a `python -m` child (`core/entry.py`; the isolation M033 kept on purpose).
  Measured in S01-T03 with the real `uv` (the full tree is in DECISIONS 2026-10-15 "One
  hop"):
  - `wiki collect --list` runs as `uv` → dispatcher → handler;
  - a bash wrapper (`wiki doctor`) runs as bash → `uv` → python;
  - both keep three processes alive at once;
  - `uv run` costs about 57 ms per call (median 82 ms against 25 ms for the venv's python);
  - `wiki collect --list` takes a median 343 ms end to end.
- **Three command tables.**
  - `scripts/cli_catalog.py` holds 48 `CommandSpec`s and renders `wiki help`.
  - `scripts/menu.py` hand-curates QUICK_ACTIONS (4), CATEGORIES (6 buckets) and
    FUZZY_CATALOG (~49) for the TUI.
  - `scripts/core/actions.py` holds the schema-2 action catalogue behind `menu --json` and
    the desktop app.
- **Consumers of the entry.** All of them call `<vault>/.wiki/wiki` and must keep working:
  - the desktop app (`desktop/src/vault/wiki-exec.ts:wikiBin`);
  - the Obsidian shell-command buttons (8 in `templates/.obsidian/plugins/obsidian-shellcommands/data.json`);
  - `skills/use-llm-wiki/SKILL.md`;
  - the `~/.local/bin/wiki` symlink that `install-shortcut` creates (live: points at the lxw
    vault's entry).
  - Agent hooks do not go through `wiki`. They are installed as `cd <.wiki> && uv run python
    hooks/<x>.py`.
- **Tests on the bash layer: 10.** `test_wiki_update.py` 2, `test_bash_json_banner.py` 2,
  `test_hooks_merge.py` 5, `test_seed_preserves_caches.py` 1. M033's oracle
  (`tests/_oracle.py`) snapshots `menu --json`, `doctor --quick --json` and `cli.py help`,
  not the bash commands.
- **Other measurements.** 532 `print(` calls in `scripts/`. `README.md` 378 lines (rule
  ≤ 300), `AGENTS.md` 323. The TUI header shows ✨ and the commit hash.
- **Carried from M033** (its closing reassessment):
  - `backlog/lazy-collector-registry.md`: registration on package import costs every collector
    verb ~0.25 s and forced three entry scripts.
  - `backlog/collect-flags-one-verb.md`.
  - `print` → `core/console`.

## Exit criteria

1. **Bootstrap.** `wiki` is at most 150 lines of bash: symlink resolution, the vault guard,
   venv resolution and an `exec`. `lib/*.sh` is gone. `install.sh` stays the pre-venv
   installer in bash, because it runs before uv and the venv exist.
2. **One hop.** `wiki <cmd>` execs the venv's Python directly: no `uv run` per call when the
   venv exists, and a fresh vault falls back to `uv run`. Every command goes through the
   Python dispatcher, the 14 bash ones included. The dispatcher and at most one handler
   process remain (open question 1).
3. **Behaviour held, proven.** An extended oracle records each bash command's observable effect
   *before* it is ported, on a fixture vault and a fixture `HOME`, and compares after:
   - the help, version and status text;
   - `config get/set`;
   - the merges `hooks install/uninstall` makes into agent configs;
   - `skills install/sync/status`;
   - `seed` onto a fixture vault;
   - `install-shortcut`;
   - `update` on a scratch clone.

   A deliberate difference is decided in its commit, never silent.
4. **One table.** `wiki help` and the home menu derive from one catalogue. A test refuses a
   menu entry whose argv names no catalogue command; the TUI's hand-curated lists are gone.
5. **One output path.** Command output goes through `core/console`. A gate refuses `print(` in
   command modules outside an allowlist with reasons. The TUI's ✨ and commit hash are gone.
6. **Collectors.** A name → module table registers collectors lazily (`wiki collect --list`
   imports no collector module). `wiki collect <name> -- <flags>` passes flags through, and
   the three by-path entry scripts are deleted.
7. **Surfaces cut.** `README.md` ≤ 300 lines and `AGENTS.md` ≤ 250, each section kept for a
   named reader.
8. **Operator path proven.** On a scratch vault, `wiki update` goes from 0.7.3 to the M034
   engine end to end (pull, `uv sync`, migrations, the post-pull re-exec). The desktop app,
   the Obsidian buttons and `~/.local/bin/wiki` keep working. `wiki setup` completes on a
   fresh scratch vault.
9. **Release.** Engine **0.8.0**, with a CHANGELOG "For your vault" section. The backlog is
   reconciled at the close.

## Size

L — see `M034-ROADMAP.md`. The arc table said M. The measurement says otherwise: 1,827 lines
of `lib/` bash, the 708-line seed merge, a self-updating `update`, and three command tables.

## Decisions locked in discuss phase

- 2026-10-15: **Entry path is fixed.** `<vault>/.wiki/wiki` stays the entry. The desktop app,
  the Obsidian buttons, the skill and the shortcut symlink call it, so none of them changes
  how it invokes the engine.
- 2026-10-15: **Hook commands stay byte-identical.** The installed agent hook commands keep the
  exact `cd <.wiki> && uv run python hooks/<x>.py` shape (with the `UV_PROJECT_ENVIRONMENT`
  prefix for cloud-synced vaults). Porting `hooks install` must not churn every operator's
  agent configs; `test_hooks_merge.py` pins the shape.
- 2026-10-15: **Oracle before port.** Every port records the bash behaviour into the oracle
  *first*, in its own commit, then ports and compares. This is M033's behaviour-oracle
  discipline applied to bash.
- 2026-10-15: **Writes outside the vault keep the backup rule.** Agent configs and shell rc
  files get the `.bak-<ts>` copy that `lib/common.sh:backup_file` makes today. No write
  outside `<vault>/` and the agent / shell config files the bash already touches.
- 2026-10-15: **No soft deprecation.** A `lib/*.sh` file is deleted in the commit that ports
  its last caller; there is no bash fallback path.
- 2026-10-15: **No config knob unless needed.** If one is added, the migration lands in the
  same commit (CLAUDE.md).
- 2026-10-15: **Release 0.8.0 at closeout.** The entry and the update path change, and
  operators reach them via `wiki update`.
- 2026-10-15 (S01-T03, was open question 1): **One hop keeps the handler child.** The
  bootstrap execs the venv's Python straight into `cli.py`, with `uv run` only when there is
  no venv yet. The handlers stay `python -m` children: dispatcher + handler, two processes.
  - In-process dispatch is rejected on counted grounds: of the 29 handlers, 9 write the
    environment at import, 20 set up the root logger, and 27 exit via `sys.exit`.
  - The hop must keep `uv run`'s implicit sync of a changed `uv.lock`.

  DECISIONS 2026-10-15 "One hop".
- 2026-10-15 (S01-T03, was open question 2): **No `llm_wiki` rename.** It would touch 335
  Python files (1,590 import lines) plus 24 other files, and no consumer imports the engine
  as a package. DECISIONS 2026-10-15 "The `llm_wiki` package rename is dropped".

## Open questions

1. *(Decided 2026-10-15: see the locked decisions above.)*
2. *(Decided 2026-10-15: see the locked decisions above.)*
3. **Interactive prompts in Python** (the setup wizard's confirm / ask / select).
   **Recommendation:** small helpers on `core/console` next to `read_key`, with no new
   dependency in every operator venv. The wizard has about ten prompts, and `questionary` /
   `InquirerPy` would pull prompt_toolkit into each vault. Decide in S02, with OSS-first
   weighed in the decision.
4. **Seed's merges.** **Recommendation:** port the jq merges to Python `json` with a parity
   harness. The fixture vault plus a read-only copy of the live vault's `.obsidian/` is the
   shape oracle (the memory "round-trip on the real data shape"). `backlog/seed-semantic-diff.md`
   (the `--check` engine-relevant subset) folds in if the port makes it cheap. Decide in S04.

## Carried from M033

- `backlog/lazy-collector-registry.md` → exit criterion 6.
- `backlog/collect-flags-one-verb.md` → exit criterion 6.
- `print` → `core/console` across the CLIs → exit criterion 5.
