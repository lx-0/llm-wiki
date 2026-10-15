---
milestone: M033
slice: S04
task: T06
project: llm-wiki
closed: 2026-10-15T13:40:12+02:00
verification: passed
---

# M033-S04-T06 -- Summary

## Commits

- `2dfea7b` -- planned + the eight characterisation test files (84 cases, green on the
  committed code)
- `6ab0e39` -- (A) the curiosity producer
- `8b46f21` -- (B) the takes + intents producers
- `8372d9d` -- (C) the reports + study
- `e68299c` -- (D) the three CLIs
- `960a74e` -- (fix) `--json` invocations print the payload alone

This summary, the slice-plan flip, STATE and the backlog note follow under the same ref
(`git log --grep '^M033-S04-T06'`).

## Outcome

The eleven functions read as their section lists, split in four commits that each left the
suite, the gate and the parity dump green:

| function | before | after |
| --- | --- | --- |
| `curiosity/producer.maybe_generate_curiosity_requests` | 310 | 147 |
| `curiosity/producer.maybe_generate_folder_requests` | 220 | 118 |
| `facts/takes_producer.maybe_extract_takes` | 164 | 48 |
| `producers/intents.IntentsProducer.run` | 159 | 59 |
| `reports/_engine/lib/render_summary.render_summary` | 234 | 85 |
| `reports/_engine/runner._persist_report` | 174 | 55 |
| `reports/_engine/runner.run_inference` | 174 | 120 |
| `study.cmd_run` | 218 | 74 |
| `query.main` | 253 | 70 |
| `suggestions/cli.main` | 169 | 24 |
| `health.render` | 165 | 28 |

The ALLOWLIST now holds only T07's `core/health.check_piggyback_health` (166), the one
function of 1,501 at or over 150 lines. The curiosity passes share the drop-summary line
through one helper; the SDK producers read gate → query → parse → write; the renderers read
frontmatter → sections; the CLIs read parser → validate → dispatch per flag.

Pure moves. The string-literal diffs are docstrings plus dedups: the two drop-summary
formats became one `%s:` template, five `"seconds"` stamps became `_stamp`, seven
`"failed"` result shapes became `_failed`, and `_domain_note` returns `""` for no domain.
The oracle `/tmp/t06-parity.py` drives the eleven entry points over 135 fixture scenarios.
It uses fake Ollama and fake SDK streams, a fake `infer_batch`, scripted input and a fixed
clock, and renders `health.render` on a fixture vault, the scratch vault and the live vault
(read-only). The dump is byte-identical before (a detached worktree at `2dfea7b`) and after
each of A–D. The normalisation covers real-clock stamps, tmp roots, checkout paths and
moved traceback frames, never behaviour.

The plan's live check found a defect. `wiki query --brief --json` on the scratch vault
returned rc 0 and the four keys, but stdout began with the dispatcher's banner (`wiki query`
plus a blank line). `960a74e` makes `--json` in the args skip the banner, in
`cli.run_command` (query, usage, publish) and through `lib/common.sh:wants_json` for the
bash-native `wiki dream list-candidates --json`. RED was observed on all four; the pins are
`tests/test_cli.py::test_json_invocation_prints_no_banner` and
`tests/test_bash_json_banner.py` (real bash layer, stub `uv`). Re-verified live on the
scratch vault at engine `960a74e`: `wiki usage --json` (the same dispatcher branch as
query, no LLM call) and `wiki dream list-candidates --json` both print pure JSON. The query
run's payload behind the old banner was the clean four-key object.

## Deviations from plan

- The fix commit was not in the plan. The plan's own live check surfaced the defect, and it
  shipped in its own commit with tests, per the slice rule. The desktop keeps its
  first-`{` parse for version skew; its comment and test title now say so. `docs/cli.md`
  and KNOWLEDGE carry the rule.
- The query was not re-run live after the fix. A brief query costs about 294 k
  cache-inclusive input tokens on the scratch vault. The same dispatcher branch was
  verified live through `wiki usage --json`.
- The "before" dump ran from a detached worktree at the plan commit, because the group
  commits changed the tree under the oracle. The normaliser grew per round to cover
  checkout paths, frame names and the oracle's own frames.
- The oracle's `run_inference` main scenario first wrote `o/phq-9.md` into the repo root
  through a relative `--output-dir`. The stray file was untracked and never committed; it
  was removed, and the scenario now writes into a tmp dir.
- `run_inference` stays at 120 lines (the operator-answers, scoring and print narrative),
  under the gate but not the ~50 the plan sketched.
- The D commit message says `health.render (165 → 30)`; measured after formatting it is 28.
- Plan command 2 expects `0`, but `fn-length-q`'s own `# total` line makes `grep -c -v`
  print `1`. The only function line is `check_piggyback_health`.

## Follow-ups

- `.ytstack/backlog/report-engine-version-stamp.md` (indexed, S): four report writers stamp
  a frozen milestone id as `engine_version` and nothing reads it. The proposal is the real
  engine version.
- The moved-verbatim cosmetics: `render_summary` numbers two comments "4.", and
  `study._retry_deferred` keeps its inline `import time as _time_mod`. The `print`
  reporting in `run_inference` / `study` is M034's `print → core/console` item.
- KNOWLEDGE: "`--json` means stdout is the payload alone — the dispatcher's banner
  included".

## Verification

Plan command 1: targeted set `416 passed`; `uv run pytest -q` **2229 passed, 1 skipped**;
`ruff check` `All checks passed!`.

Plan command 2: `"scripts/core/health.py::check_piggyback_health": 166` plus
`# total >= 150: 1 of 1501 functions`.

Plan command 3: `PARITY IDENTICAL` (135 scenarios).

Desktop: `npm run typecheck` reports 0 errors and `vitest run src/vault/query.test.ts`
reports 4 passed. shellcheck findings on `wiki` + `lib/common.sh` are unchanged (18 before
and after). CI is green on `2dfea7b`, `6ab0e39`, `8b46f21`, `8372d9d`, `e68299c` and
`960a74e`.
