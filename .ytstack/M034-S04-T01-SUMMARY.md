---
milestone: M034
slice: S04
task: T01
project: llm-wiki
closed: 2026-10-16T01:30:00+02:00
verification: passed
---

# M034-S04-T01 -- Summary

## Commits

- `119c5d5` -- M034-S04-T01: the bash seed recorded on 13 more cases, after its fixes (0.7.20, 0.7.21) — and the oracle pins large files by content again
- `5219bbc` -- M034-S04-T01: wiki seed says what it did (0.7.21) — the recording's second group: messages that named the wrong cause, writes nobody asked for
- `ee4adb9` -- M034-S04-T01: dashboard buttons wired in every vault (0.7.20) — recording the bash seed found the chain behind them broken
- `7fbcf49` -- M034-S04-T01: planned — S04 re-cut to 5 tasks with S03's lessons (record first + fix first, the pure core, the pure merges, the command, install.sh + deletion); the planning reading found install.sh sources lib/seed.sh before its venv exists, so it will seed through wiki seed after uv sync. Open question 4 decided in DECISIONS: seed's jq merges become Python json held to the bash by recorded goldens. T01 records eight bash seed cases the six existing ones miss

## Outcome

The bash `wiki seed` is now recorded on 13 more cases, 19 seed goldens in all. The goldens
were written after the bash was fixed, so T02–T05 port the fixed behaviour. The recording
turned up two groups of defects. Each was fixed in the bash first, with tests seen red, and
released.

**0.7.20 — the dashboard's buttons.**

What was broken:
- A fresh vault never got the Shell commands config, so five buttons were dead in every new
  vault (since 2026-05-02).
- The engine's own commands never reached an existing config. lxw's "refresh stats" button
  still runs a script that has moved.
- `btn-dream-cycle` and `btn-orchestrate-tasks` were in no Meta-Bind registry, in any vault.
- The template's id-keyed `shell_commands` would have lost every id in the merge.

What changed:
- Both registries go through one by-id, in-place merge (`_merge_registry`).
- The agent entries are generated only (`dashboard.agent_buttons meta-bind-templates`).
- The engine ships the icon names the plugin migrates to.
- The dashboard template is synced with the generator, and the dead `_dashboard-buttons`
  embed is gone.

A dry run on a copy of lxw's `.obsidian/` changed exactly what it should: the refresh-stats
command, the two missing buttons, and three tooltips.

**0.7.21 — what seed reports.**
- A config that is not JSON is named as such. `--extract-custom` now refuses it with exit 1;
  it used to die silently with exit 2.
- A broken overlay leaves its file alone. `--force` used to write the bare template over that
  file.
- A path that matches nothing exits 1 with the complete list of seedable paths.
- The drift advice is the targeted `--force`.
- The plugin-list merges write only when they add something.

The oracle pins large files by content hash again; its revision rule had erased every hash.

## Deviations from plan

- **The eight planned cases became 13:**
  - the legacy object form;
  - four the fixes added: `seed-check-unseeded`, `seed-check-broken-json`,
    `seed-extract-custom-broken-json`, `seed-force-broken-overlay`.
- **Two releases landed inside a recording task**, under the fix-first rule. The defects
  were dead buttons in every vault, larger than "a message".
- **Outside the planned files:**
  - Python: `scripts/dashboard/agent_buttons.py`. It now emits list-form shell commands, has
    the new `meta-bind-templates` mode, has no defs region, and gives a `no-region` verdict.
  - The templates: the shell-commands config is in list form without the agent entries; the
    meta-bind config has no agent buttons; `dashboard.md` is synced;
    `_dashboard-buttons.md` is deleted.
  - `tests/_oracle.py`: the hash fix, with its guard.
  - The new test modules `tests/test_agent_buttons.py` and `tests/test_seed.py`.
- **The live dry run happened in T01**, though the plan had it in T03. Only the copy showed
  the plugin's own migrations.

## Follow-ups

- **T03 ports the merges as they stand now:** `_merge_registry` and `_merge_list_union`, not
  the pre-0.7.20 functions. The slice plan's T03 says so, and the plan notes describe the
  live-copy run.
- **For the operator** (0.7.20's "For your vault"): `wiki update`, then `wiki seed`, then
  restart Obsidian. That fixes refresh-stats and the two agent buttons in lxw. It was not
  done from here, since the live vault is read-only to this work.
- **Backlog:** `.ytstack/backlog/dashboard-agent-buttons-callout.md`. The agent buttons
  render outside the "🤖 Agents" callout. Whether they belong inside it or stay always
  visible is the operator's call.
- **Recorded:**
  - KNOWLEDGE, the 2026-10-16 section, lessons 1–7;
  - DECISIONS, the registry merge;
  - `~/.claude/TECH-PATTERNS.md`: zsh `$var:x` / `$var[…]`, and merges that must survive a
    plugin's migrations.
- **ytstack quirk, seen again:** the hook's draft named `ee4adb9` as the task's first commit,
  but the first was `7fbcf49`. It is already reported.

## Verification

Command: `uv run --frozen pytest tests/test_bash_oracle.py -q -k seed` -- passed (19 passed).
Further checks:
- the oracle, payload, seed and agent-button tests: 120 passed;
- the full suite at 0.7.21: 2531 passed, 1 skipped. Its six failures were this task's
  cases, still uncommitted at the time; they are recorded green in `119c5d5`.
- the full suite at `119c5d5`: 2542 passed, 1 skipped.
- CI: green on `ee4adb9`, `5219bbc` and `119c5d5`.
