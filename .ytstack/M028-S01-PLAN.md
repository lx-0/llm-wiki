---
milestone: M028
slice: S01
project: llm-wiki
created: 2026-06-13T15:56:13+0200
revised: 2026-06-13T16:10:00+0200
status: planned
task_count: 6
completed_tasks: 5
---

# M028-S01 -- Slice Plan

**Goal:** `apply()` becomes **structurally** non-destructive — the agent can no
longer shell out or delete (Bash dropped + path-scoped), it annotates superseded
articles instead of deleting them, and `apply` reports the *real* filesystem
delta. Trust model: **agent proposes, engine disposes.**

> Revised after plan-eng-review (2026-06-13): the sandbox was pulled forward from
> S02 into S01. Stopping the data loss via prompt alone is prompt-compliance —
> the structural stop is removing `Bash` so the agent *cannot* `rm`/`git mv`,
> regardless of what the prompt says. Opt-in deletion (the only path needing the
> `.trash` executor) moves entirely to S02.

## Tasks

- [x] T01 -- Sandbox `apply()` in `correct_apply.py` (L120-131) by mirroring
  `reconcile_fact()` (L233-252): drop `Bash` from `allowed_tools`
  (`["Read","Glob","Grep","Write","Edit"]`), add a `PreToolUse`
  `HookMatcher(matcher="Write|Edit", hooks=[make_path_scope_hook(...)])` scoping
  writes to `knowledge/` (minus `facts/`), `daily/`, `index.md`, and the
  operations log; switch `permission_mode` to `default`; bound `max_turns` via a
  new config knob (`correct_apply_max_turns`, migration same-commit). This is the
  HARD non-destructive guarantee — the agent can no longer delete or shell out.
- [x] T02 -- Extend `make_path_scope_hook` in `scripts/core/sdk_helpers.py:404`
  with an optional `denied_subpaths` param (deny a write even when it resolves
  inside an allowed root) so `knowledge/facts/` stays write-protected while the
  rest of `knowledge/` is writable. Today the hook is allow-list-only — there is
  no way to express "knowledge/ except facts/". Unit-test the hook directly
  (allow knowledge/concepts, deny knowledge/facts, deny raw/).
- [x] T03 -- Rewrite the negation branch of `prompts/correct_apply.md` (L25-26 +
  the `## Applied summary` block L45-50): for `status: negation`/`supersession`,
  **annotate** — add `status: superseded` + `superseded_by: facts/${slug}` +
  `outdated_since: ${today}` to the article frontmatter and prepend a one-line
  banner under the H1 pointing at the fact. Add verbatim: "outdated != false —
  if the claim *was* true and is now superseded, annotate; never delete history."
  The agent does annotations via Write/Edit only and emits a structured
  **proposal block** for any rename it judges necessary (consumed by T04).
  Deletion is NOT available in S01 — state that explicitly (deferred to S02's
  safe executor).
- [x] T04 -- Engine-side rename helper for the disambiguation path (replaces the
  removed Bash `git mv`): parse the agent's structured rename proposal, perform
  the file move + rewrite every `[[wikilink]]` via the `core.links` resolver,
  update `index.md`/title frontmatter. Without this, disambiguation `apply` would
  silently half-work once Bash is gone.
- [x] T05 -- Ground-truth reporting in `correct_apply.py` (replace the bare
  `print(result_text)` at L153-154): compute the real delta — `git status
  --porcelain` when `ROOT_DIR` is a git repo, else a pre/post mtime+hash snapshot
  of `knowledge/` + `index.md` + the renames the engine performed — print
  created/modified/renamed counts + paths, and `log.warning` when the agent's
  `## Applied summary` diverges from the filesystem truth.
- [ ] T06 -- Golden test reproducing issue #5 (RED first): a `negation` fact with
  a broad term over a fixture vault deletes **0** articles (annotates instead);
  the path-scope hook denies an out-of-`knowledge/` write attempt; the printed
  delta equals the git delta; the divergence WARNING fires on a stubbed lying
  summary.

## Done when

All tasks `[x]` and verified. `apply()` cannot delete or shell out; a broad-term
negation fact annotates instead of deleting; reporting is filesystem-grounded.

## Notes

- Deletion gate (`--allow-delete` / `disposition: delete`) + the `.trash`
  executor live in S02 — S01 has no deletion path at all, which is the point.
- T03/T04 share one structured-proposal contract (what the agent wants
  changed: supersede list + rename list). S02 extends the same contract with a
  delete list. Design the schema once in T03.
- DRY: T01 and `reconcile_fact()` will share most of the `ClaudeAgentOptions`
  block — extract a helper rather than copy-paste the options.
- T03 is a `[→EVAL]` change (prompt behaviour); T06's golden test is the eval.
