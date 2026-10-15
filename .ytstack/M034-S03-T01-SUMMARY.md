---
milestone: M034
slice: S03
task: T01
project: llm-wiki
closed: 2026-10-15T22:50:00+02:00
verification: passed
---

# M034-S03-T01 -- Summary

## Commits

- `f3b1d69` -- M034-S03-T01: core/agents.py — the agent registry in Python, one hook-command grammar, hook_cmd and the per-agent payloads byte-identical to the bash jq output; doctor reads it
- `c5db568` -- M034-S03-T01: shell-quote every path the engine hands to another shell — an apostrophe in the vault path broke every agent hook (release 0.7.15)
- `0295f76` -- M034-S03-T01: planned — core/agents.py: the registry, one hook-command grammar, hook_cmd, payloads byte-identical to the bash jq output

## Outcome

`scripts/core/agents.py` (ty-gated) holds the agent registry: claude / codex / gemini /
cursor, each with its detection dir, config file and hooks, plus Cursor's flat schema. It
also has the scopes and config paths, and **one** hook-command grammar (`HOOK_CMD_RE`, the
probe's union with `_transcript`) with `is_wiki_hook` and the text probe `hooks_installed`.
`shell_quote` + `hook_cmd`, `payload` and `render` produce, for every agent, the text of the
bash `agent_payload | jq .` byte for byte: plain, iCloud and apostrophe vaults. Doctor's
`hooks-installed` check reads the registry and the grammar instead of its own copies, with
the same raw-text semantics and the same output. Engine 0.7.15.

## Deviations from plan

- **A bash-first release came first (0.7.15, `c5db568`).** Porting `hook_cmd` found the
  path wrapped in bare `'…'`. For a vault named "Alex's Vault" every hook died with exit 2,
  and no session was captured. A repo-wide grep found the same defect class in four pasteable
  hints. The hop's sync hint (0.7.12) and `wiki update`'s retry line were unquoted, so
  `Mobile Documents` split `--project`. The update line and doctor's
  `dependencies-importable` fix also left out the environment, so in a cloud vault they
  rebuilt `.wiki/.venv` in the vault. `wiki update`'s `rm -rf` hint broke on an apostrophe.
  All five now go through `lib/common.sh:shell_quote` / `sync_hint` (doctor: `sys.prefix` +
  `shlex.quote`). Hook commands for paths without an apostrophe are unchanged: the oracle
  goldens and `test_hooks_merge` pass as they were.
- **Something calls the module already.** The plan said "nothing calls it yet", but the
  repo-wide grep found a fourth copy of the grammar, with its own registry, in
  `core/health/environment.py`. It now reads `core.agents`.
- **Beyond the plan's two files:**
  - a seam guard: no second grammar under `scripts/` or `hooks/`; its pattern matches the
    doctor copy this commit removed;
  - the parity test runs over `AGENTS`, so an agent added in Python only fails it;
  - `docs/engine-layout.md`: agents.py in the core tree, a seam row, and the `lib/` listing
    corrected (skills.sh and seed.sh were missing; `ask` and config.sh's wizard were stale);
  - `AGENTS.md`'s add-an-agent recipe names both registries while `wiki hooks` is bash.

## Follow-ups

- **S03-T05** (the port; the slice was split three times after this task): the probe reads the file as text
  (like the bash `grep`). It says "installed"
  for a wiki command string anywhere in the file, even outside `hooks`, and misses
  JSON-escaped forms (`\"`, `\/`), which the merge's decoded match catches. Decide whether
  `hooks status` walks the hook entries, as the merge and uninstall do. If so, fix it in the
  bash first, then record.
- **S05:** `core/health/engine.py:_CLOUD_PATH_MARKERS` is a second copy of
  `lib/common.sh:wiki_path_is_cloud_synced`. When lib/common.sh retires, give the rule one
  home, or a parity test if the bootstrap must keep a bash copy.
- **S03-T07:** `docs/FEATURES.md`, `docs/PROCESS.md` and `AGENTS.md` still name
  `lib/agents.sh` as the registry. Correct while `wiki hooks` is bash; T07's docs pass
  updates them.
- **Recorded:** KNOWLEDGE.md ("A path inside a command for another shell…") and
  ~/.claude/TECH-PATTERNS.md (Build, Deploy & Tooling).

## Verification

Command: `uv run --frozen pytest tests/test_agents_registry.py -q` — passed (22). `uv run
--frozen --group typecheck ty check scripts/core` — passed. Full suite 2455 passed,
1 skipped. Seen to fail: RED on the missing module, and four reintroduced bugs each fail a
test (bare quoting, Gemini timeouts in seconds, the merge's grammar without `_transcript`,
a Python-only agent). CI green on `c5db568` and `f3b1d69` (2455 passed on the runner's
bash 5).
