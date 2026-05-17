# commit_article via manifest emitter — deferred from M018-S03

Surfaced 2026-05-17 when M018-S03 ("extract `commit_article()` pure I/O") hit a premise-broken finding: there is no Python write logic to extract. The SDK agent owns `knowledge/` writes via tool-use.

## What the original design wanted

From `.ytstack/backlog/producer-seam.md`'s Milestone-B section: `compile_source` is a pure LLM call, `commit_article` is pure file I/O. Python decides AND executes the write; the LLM emits content only.

## What today's code actually does

The compile agent has `Write(knowledge/**)` + `Edit(knowledge/**)` in `allowed_tools` (legacy branch) or the `make_path_scope_gate([ROOT_DIR / "knowledge"])` callback (`features.compile_callback_gate=true`, default since `d8a0de5`). Inside `compile_source`'s SDK call, the agent:

- Reads the existing target file (if any) to learn operator-edited frontmatter (`pinned:`, `dream_priority:`, `domain:`, `compile_role:`, `author:`)
- Decides on frontmatter merge — preserves operator keys, overwrites engine keys
- Distinguishes `## State` (overwrite-on-compile) from `## Timeline` (append-on-compile) for entity pages under `knowledge/people/` and `knowledge/projects/` (M005)
- Updates `compiled_from:` provenance list
- Updates `knowledge/index.md` row (creates / replaces in place)
- May touch SECONDARY knowledge files in the same compile — e.g. a transcript compile updates the speaker's `people/<name>.md` Timeline, references a project's `projects/<slug>.md` State, creates a new `connections/<source>—<target>.md` article. ONE source → N file mutations, agent-orchestrated.
- All decisions encoded across the substrate prompts (compile_main.md is the heaviest carry-forward prompt; per-substrate variants override).

Python sees the agent's free-text Final-Response (`CompileResult.article`) but does not parse it for write-targets. Today's `article` field holds whatever the agent narrates ("Done. Wrote knowledge/concepts/X.md and updated people/Y.md."), not structured output.

## What a real `commit_article` would require

1. **Strip Write/Edit from the agent's `allowed_tools`.** Agent becomes read-only over the vault.
2. **Rewrite every substrate prompt** to emit a structured manifest as final response. ~8 prompts: compile_main, compile_daily, compile_calendar, compile_health, compile_screenshots, compile_pictures, compile_memories, compile_default (plus any future ones). The manifest shape needs to support:
   - Multiple file targets per compile
   - Per-target operation kind: `create` / `overwrite` / `append_section(name)` / `replace_section(name)` / `frontmatter_merge`
   - Per-target content body
3. **Manifest parser.** Robust to LLM variation — JSON schema, validated, with fail-soft on partial manifests.
4. **`CompileResult.outputs: dict[Path, FileOp]` contract change.** The single-target `article: str | None` field today doesn't represent multi-file output. Replacing it is a breaking change to compile_source's interface (and to S02's existing tests).
5. **`commit_article(result: CompileResult, vault_root: Path) → None`** iterates `result.outputs` and applies each FileOp atomically — frontmatter merge with preserved operator keys, atomic-replace, knowledge/index.md row maintenance.
6. **Equivalence tests.** Some way to verify the manifest-driven writes produce the same `knowledge/` state as today's agent-tool-use writes. Hard against LLM non-determinism (see S01 cancellation) — likely needs structural-match tests, not byte-identical.

## Why this is its own milestone, not a slice

- Touches every substrate prompt — LLM-output-quality risk surface is large
- Breaking contract change to `CompileResult` (S02 tests need rework)
- Multi-week verification cycle on lxw before flipping default
- Possible feature regression: today's agent can refactor knowledge/ structures fluidly during compile (rename a concept, split an article in two, merge two related notes). A manifest restricts the agent to declarative output — fluid restructures become harder.

## When to revisit

- When a concrete blocker shows up that requires Python-side write control:
  - Atomicity bug (today multiple agent Write/Edit calls aren't atomic across a single compile)
  - Audit trail (need to log every knowledge/ mutation, not just trust the agent's narration)
  - Cross-vault sync (need to mirror compile output to a second vault)
  - Property-based testing of write behavior (frontmatter merge invariants, etc.)
- Or when the operator explicitly chooses to invest in the architecture pivot for its own sake.

Until then: agent-side writes are the contract. M018 ships as S02 (compile_source extraction) + S04 (post-pass lift).
