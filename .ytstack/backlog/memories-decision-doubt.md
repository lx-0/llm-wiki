# Operator doubts the 2026-05-13 memory-substrate phase-out decision

**Opened 2026-05-18 by operator.**

The 2026-05-13 DECISIONS entry "Memories are not a substrate — hard-remove sync-memories + seed + raw/memories/ wiring" rests on the claim that memories are downstream of sessions (sessions captured via daily/, so memories double-count).

**Operator pushback (verbatim concept):**

> "ich sehe nicht dass memories downstream von sessions sind, weil die sind ja distilled from sessions. das ist ja nicht-deterministisch!!! warum sollten wir sowas excluden??"

**Distilled argument:** memories are NON-DETERMINISTIC distillations from sessions. Even if the raw session is in daily/, the LLM's distillation (the memory itself — what Claude judged worth remembering, in what shape, with what wording) is a separate signal that no future session can regenerate from the daily/ alone. Excluding memories on a "doubly-captured" framing assumes deterministic recoverability, which doesn't hold for LLM-distilled artefacts.

**Pending:**

1. AI opinion logged below
2. Karpathy + Cole Medin sources researched
3. General best-practice research (KB-source-selection)
4. Final recommendation + DECISIONS supersedes/confirms

**Status:** open, in-research.

---

## AI Opinion (registered 2026-05-18, pre-research)

The 2026-05-13 decision-body rests on "memories are downstream of sessions" + "double-counting". This conflates:

- **Verbatim duplication** (regenerable from upstream — would correctly be double-counted)
- **LLM-distillation** (non-deterministic, Claude's editorial choice of what 3 patterns to keep, in what wording, with what `Why:`/`How to apply:` structure — NOT regenerable from the original session)

Memory files are the second class. Re-deriving from daily/sessions would produce *different* memories. The decision's regenerability premise doesn't hold.

Additionally, AGENTS.md / CLAUDE.md files in `~/.claude/projects/*/memory/` are NOT session-distillates at all — they're manually + iteratively curated over weeks. The decision treated all memory-files as auto-rewrites, blind to the hand-curated portion.

The broken-link symptom (502/584 dangling) was already addressed by the 2026-05-04 "Distill, don't cite" decision (body-wikilink ban + `compiled_from:` metadata). Adding substrate-exclusion on top was over-rotation.

## Research findings (2026-05-18)

### Karpathy LLM Wiki

- Gist describes raw/ as "source of truth, LLM reads but never modifies"
- Does NOT explicitly address whether LLM-derived artefacts feed back as substrate
- Multiple commenters (mikhashev, jianghailong-xy, nowissan) identified this gap and proposed **provenance-tracking + source-taxonomy** as the answer — NOT substrate-exclusion
- The 2026-05-13 decision's claim "Karpathy doesn't mirror auto-memory" is technically true (he doesn't address it) but reads silence as endorsement of exclusion, which the gist does not provide

### Cole Medin claude-memory-compiler

- README input: session transcripts (Claude project-memory files not explicitly addressed)
- BUT: he has separate `memory.md` that's LLM-curated-promotion from daily logs → durable permanent record
- Treats LLM-distilled memory as **first-class durable artefact** distinct from raw session log
- 2026-05-13 framing "Cole captures transcripts only" was incomplete — he also has the promoted memory.md layer

### Industry PKM (2026)

- Dominant pattern when LLM-derived content mixes with original sources: **provenance-tracking + frontmatter-tagging** (e.g. `source_type: llm_distilled`)
- The risk "synthetic content being re-synthesized (compounding distortion)" is addressed by metadata + lifecycle rules, NOT by exclusion
- Source: knowledge-distillation papers + PKM blog post round-up (2026)

## Final Recommendation

**REVERSE the 2026-05-13 hard-removal decision.** Re-architect memory as first-class substrate with provenance:

1. **`select_files` re-includes `raw/memories/`** — un-do both the 2026-05-13 exclusion AND the 2026-05-16 band-aid (cheap-prompt-for-leftover-files). Memory is substrate, full citizen.

2. **Memory-files compile to concepts / connections / people / projects** — drop the "only Timeline-append on existing project" constraint (`scripts/compile_stages/memory.py:resolve_project_slug → None → skip`). Let the compile prompt distill naturally.

3. **Provenance via frontmatter** — every compiled output from a memory source carries `compiled_from_distilled: true` so future compile passes know "this is operator-iterative-learning, not first-hand evidence". Mitigates the compounding-distortion risk per industry pattern.

4. **2026-05-04 "Distill, don't cite" stays unchanged** — body-wikilinks ban + `compiled_from:` metadata. That decision was the correct fix for broken-links, separate from the substrate question.

5. **Optional: snapshot-pattern instead of mirror-prune** — content-hash paths in `raw/memories/`, never delete. Solves the broken-link root cause (mirror-pruning) without giving up the substrate. Was variant B of the 2026-05-04 decision, was rejected then — worth re-evaluating now.

## Sources

- Karpathy LLM Wiki gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Cole Medin claude-memory-compiler: https://github.com/coleam00/claude-memory-compiler
- DAIR.AI Academy on LLM Knowledge Bases: https://academy.dair.ai/blog/llm-knowledge-bases-karpathy
- Knowledge distillation review (Springer 2026): https://link.springer.com/article/10.1007/s10462-025-11423-3
- PKM with LLM distillation (Bosio 2026): https://bosio.digital/articles/llm-knowledge-bases-living-intelligence

## Status

Recommendation: REVERSE 2026-05-13 decision. Awaiting operator decision to formalize a new DECISIONS.md entry that supersedes 2026-05-13.

---

## SHIPPED 2026-05-18 14:27 — live-verified on lxw

Full implementation arc:

| Commit | Change |
|---|---|
| `1cf23b0` | Reversal core: pre-pass drops `_skipped: memory_no_project_page`, falls through to Mode B. `prompts/compile_memories.md` rewritten with Mode A (project page → Timeline-append, 2 turns) + Mode B (no project → distill to `knowledge/concepts/<slug>.md`, max 5 Edits + 3 Writes, with `compiled_from_distilled: true` frontmatter). `SUBSTRATE_PROMPTS` memory max_turns 5 → 20. DECISIONS supersede entry. |
| `8918d21` + `dd6c00d` | Migration `LIST_REMOVALS` extended: `memory-sync` + `memory-seed` removed from `limits.compile_skip_substrate_types`. Operator vaults had these in the skip-list (added during 2026-05-13 → 2026-05-16 wind-down/band-aid). The skip fired in `compile.py:567` BEFORE the substrate-dispatch could reach the new Mode A/B logic. `wiki update` migrates operator config on next pull. |
| `f4865b3` | Drop `"instructions"` ClassifyKind. The classifier from 2026-05-18 morning routed AGENTS.md/CLAUDE.md/README.md memory files to `compile_instructions.md` (max 2 Edits, no concept stubs). After the Mode B path landed, the classifier intercepted those same files and dropped them into a 0-writes path. Removed the routing; AGENTS/CLAUDE/README memory files now flow through `compile_memories.md` Mode B naturally. The `compile_instructions.md` prompt file stays in `prompts/` (no deletion of historical artefacts) but is no longer reachable from dispatch. |

**Live verification (lxw, 14:27):**

```
file:    raw/memories/home-alex-Code-WebDev-projects-yesterday-ai-company-orga__AGENTS.md
shape:   6 H2 sections → aggregated-memory chunking
calls:   6 chunks × ~30s each → all ok
cost:    $0.28 total
output:  5 new knowledge/concepts/ articles
         - company-documentation-hierarchy.md
         - numbered-kebab-case-convention.md
         - yesterday-ai-company-orga-repos.md
         - cross-repo-naming-convention-divergence.md
         - (+1)
```

All five concepts carry `compiled_from_distilled: true` frontmatter (per the new convention).

**Open follow-ups (low-priority):**

- ~33 other memory files in `raw/memories/` (no project page, never compiled) will Mode-B-distill on the next compile run. Signal-to-noise review after that pass decides whether the 3-concepts-per-memory cap is right.
- Architecture diagram (`docs/architecture.excalidraw`): `raw/memories/` was removed from the substrate row in the 2026-05-13 phase-out; should be re-promoted to first-class substrate position alongside email/jamie/etc. Deferred until next docs-sync pass.
- Snapshot-pattern for `raw/memories/` (content-hash paths, never delete) is still an open future option if operator re-introduces auto-syncing — was 2026-05-04 variant B, rejected then, worth re-evaluating with current architecture.
