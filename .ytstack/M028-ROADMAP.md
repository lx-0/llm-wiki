---
milestone: M028
project: llm-wiki
size: L
created: 2026-06-13T15:51:29+0200
status: in_progress
total_slices: 4
completed_slices: 3
source_issue: https://github.com/lx-0/llm-wiki/issues/5
---

# M028 Roadmap

**Goal:** Make `wiki correct apply` non-destructive and truthful — `negation`
facts supersede/annotate by default, the engine reports the real filesystem
delta, destructive ops have a safety net, and the apply-agent is sandboxed.

**Exit criteria:**
1. `negation` annotates (status: superseded + banner) and deletes nothing by default; deletion is explicit opt-in for factually-false content.
2. `apply` prints the real filesystem delta (git porcelain / mtime+hash) and WARNs on mismatch vs. the agent summary.
3. Deletions → `.trash/<ts>/` (or refuse on dirty/non-git unless `--force`); every article backed up before edit/delete.
4. `--dry-run` shows blast radius: candidate files + planned per-file action.
5. `apply()` sandboxed like `reconcile_fact()` (no Bash, path-scope hook, bounded turns).
6. First-class `supersession` status (enum + lint + prompt).
7. Golden test: the issue's repro no longer deletes 17 articles; summary count = git delta.

## Slices

Slice detail lives in per-slice `M028-S##-PLAN.md` files, created by
`ytstack:slice-milestone`.

- [x] S01 -- Structural non-destructive guarantee (sandbox + supersede + engine rename) + truthful reporting
- [x] S02 -- Safe opt-in deletion (engine .trash executor + per-article backup + dirty-tree guard)
- [x] S03 -- Informative --dry-run (blast radius) + over-broad-term warning at add-time
- [ ] S04 -- First-class supersession status + lint + docs + closeout

### Suggested slicing (input for slice-milestone, not binding)

Sequenced safety-first — the data-loss stops at S01, polish/hardening follows:

- **S01 — Non-destructive default + truthful reporting (fixes #1 + #2).** The
  critical pair: flip `prompts/correct_apply.md` to supersede-by-default
  (`status: superseded` + `superseded_by:`/`outdated_since:` + banner; "outdated
  != false — annotate, never delete history"; deletion gated behind explicit
  signal). Add ground-truth filesystem-delta reporting in
  `scripts/facts/correct_apply.py` (git porcelain / mtime+hash snapshot) + warn on
  divergence from the agent's `## Applied summary`. Stops the bleeding.
- **S02 — Sandbox + safety net (fixes #5 + #3).** Sandbox `apply()` like
  `reconcile_fact()`: drop `Bash`, add `make_path_scope_hook`, explicit rename
  helper, bounded turns. Move deletions to `.trash/<ts>/`; back up every article
  before edit/delete; refuse destructive runs on a dirty/non-git tree unless
  `--force`.
- **S03 — Informative `--dry-run` (fix #4).** Run the candidate greps, print the
  file list + planned per-file action (edit / supersede / delete / rename). The
  single most useful guardrail — blast radius before paying. (Optionally fold the
  over-broad-term warning at `correct add` time here.)
- **S04 — First-class `supersession` status (fix #6).** Add the status to
  `facts/correct.py` enum + `lint.py` + the prompt so `negation` stops conflating
  *false* with *outdated*. Schema-migration discipline (`migrate_config_keys.py`)
  if any new config knob lands. Closeout: golden repro test, docs (AGENTS.md /
  PROCESS.md / config.md), diagrams if behaviour is portrait-worthy, close issue #5.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap`
checks if the plan still fits reality. S01 is the priority (stops data loss);
the rest hardens.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
