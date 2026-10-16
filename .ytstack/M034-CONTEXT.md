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
   - *Amended 2026-10-16 (S06-T03), with the measurement.* Importing the package imports no
     collector module, and `wiki collect <name>` imports only its own; both are tested.
     `--list` still imports every collector: the desktop's `collect --list --json` shows each
     one's `configured`, which is the collector's own `is_configured()`.
   - The criterion's premise, 0.25 s per collector verb (backlog, 2026-10-14), had shrunk to
     0.07 s for `import collectors`. Now it is 0.014 s; `all_collectors()` takes 0.066 s for
     14. DECISIONS 2026-10-16 "The collector registry is a lazy table".
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
- 2026-10-15 (S02-T01, was open question 3): **Own line-based prompt helpers on
  `core/console`.**
  - They read byte by byte, put every prompt on stderr and add no dependency.
  - questionary / `prompt_toolkit.prompt` were measured on a pipe. They warn, write a
    terminal redraw into stdout and swallow the remaining stdin.
  - The question's dependency-cost argument was wrong: `prompt_toolkit` is already in every
    vault.

  DECISIONS 2026-10-15 "Prompts in Python".

## Open questions

1. *(Decided 2026-10-15: see the locked decisions above.)*
2. *(Decided 2026-10-15: see the locked decisions above.)*
3. *(Decided 2026-10-15: see the locked decisions above.)*
4. *(Decided 2026-10-16, S04 planning: DECISIONS "Seed's jq merges become Python `json`,
   held to the bash by recorded goldens".)*

## Carried from M033

- `backlog/lazy-collector-registry.md` → exit criterion 6.
- `backlog/collect-flags-one-verb.md` → exit criterion 6.
- `print` → `core/console` across the CLIs → exit criterion 5.

## Reassessment 2026-10-15T20:26 — after S01

**Verdict: B.** The slice order holds (S02 config + setup → S03 hooks + skills → S04 seed →
S05 update + the last bash → S06 surface diet). S01 changed what sits *inside* the later
slices. The bash library files have callers in later slices, so each file now retires with
its last caller, not with the slice named after it. The locked decision "no soft
deprecation" already says "deleted in the commit that ports its last caller".

1. **`lib/config.sh` → S03-T04, not S02.** `lib/skills.sh` calls `config_get`, and
   `cmd_status` calls `config_cmd_status`. S02-T05 deletes only the functions whose last
   caller S02 ports (the wizard, `edit`, `keys`, `path`, the validators, `ask`).
2. **`lib/ui.sh` → S05-T04, not S02.** `lib/hooks.sh` (S03) uses `confirm` / `select_*`,
   and `cmd_update`'s stash prompt (S05) uses `confirm`.
3. **`wiki status` → S03-T02** (S01's re-cut). It is a banner over `config status` and
   `hooks status`.
4. **`wiki setup`'s hooks step** runs `wiki hooks install` through the entry until S03-T02
   ports hooks. That calls a not-yet-ported command through its public interface, as the menu
   does; it is not a bash fallback.
5. **S02-T01's prompt helpers read stdin byte by byte** (`os.read(0, 1)`). On a pipe,
   `sys.stdin.readline()` buffers ahead and would swallow the answers meant for that child.
6. **The help texts move with each port.** S05-T03 becomes the check that none is left
   (`cmd_help` went in S01-T05).
7. **Two leftovers are filed into S06:**
   - T01: `menu.py`'s non-TTY fallback spawns `wiki help`;
   - T03: PROCESS.md's 12 bare `uv run --project .wiki` lines.

What S01 delivered:
- 53 bash goldens;
- the one hop (two processes instead of three, ~75 ms per call);
- the catalogue machinery the later ports reuse: routes with argument prefixes, a default
  route, aliases, `takes_args`, bannerless routes;
- `wiki stats`;
- a green consumer smoke;
- engine 0.7.4 → 0.7.8.

## Re-plan 2026-10-15T23:05 — S03-T02 split after T01

S03-T02 held both the bash fixes (with their records and a release) and the port. That is two
context windows' work, so it is now two tasks:
- **T02** fixes the hooks commands in the bash and records them (0.7.16);
- **T03** ports `wiki hooks` and `wiki status`.

Skills became T04 and the deletions T05 (S03: 5 tasks). Where the S01 reassessment above says
S03-T02 (`wiki status`, setup's hooks step), it now means T03. Its S03-T04 (`lib/config.sh`)
now means T05.

**After T02 (2026-10-15T23:15), one more split.** T02's recording found the backup overwrite
(same-second backups share a name). The Python side has the same flaw, in
`core/frontmatter.backup` and dedup's copy, and the port needs a helper with the
never-overwrite rule. That helper is now its own task:
- **T03:** one backup helper, `core/backup.py`, with a seam guard;
- **T04:** the port;
- **T05:** skills;
- **T06:** the deletions (S03: 6 tasks).

So the S01 reassessment's S03-T02 means T04 now, and its S03-T04 means T06.

**After T03 (2026-10-15T23:40), the last split.** Measuring the port for its plan showed four
jobs:
- the merge and the uninstall in Python, byte-identical to jq;
- the command flows, byte-exact down to bash's byte-counted `%-30s` padding;
- the catalogue, help, setup in-process and the cleanup in `wiki`;
- the probe decision, with doctor.

The pure layer goes first, on its own:
- **T04:** `merge` / `without_wiki_hooks` in `core/agents.py`;
- **T05:** the port;
- **T06:** skills;
- **T07:** the deletions (S03: 7 tasks, the cap).

The code comments that named task numbers now name the slice, so they no longer move with
a split.
