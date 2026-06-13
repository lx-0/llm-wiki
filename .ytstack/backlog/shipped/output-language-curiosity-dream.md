# Backlog: extend `personal.output_language` to curiosity + dream render paths

**Status:** SHIPPED 2026-06-13 in **0.2.1** (curiosity + dream render paths now carry `${output_language_instruction}`; see DECISIONS 2026-06-13 follow-up entry). Live e2e still unverified (inherited from issue #4).
**Size:** S

## Context

`personal.output_language` (issue #4) forces compiled prose into a target
language. It is injected at the **single central compile render**
(`scripts/compile_stages/compile.py`), which covers all 8 substrate prompts
(`compile_main`, `compile_default`, `compile_daily`, `compile_health`,
`compile_calendar`, `compile_pictures`, `compile_screenshots`,
`compile_memories`).

Two LLM-prose producers render on **separate paths** and were deliberately left
out of the issue-#4 scope:

- **Curiosity** — `scripts/curiosity/producer.py` renders `compile_curiosity` +
  `compile_curiosity_folder` (lines ~294, ~512) directly, not through the
  compile-stages render.
- **Dream** — `dream_entity` (entity-page synthesis) renders on the dream path.

So in a German vault with `output_language: "de"`, curiosity output and dream
entity pages still follow today's source-language behavior.

## Proposal

Reuse the existing pure helper `core.prompts.build_output_language_instruction`:

1. Add `${output_language_instruction}` to `prompts/compile_curiosity.md`,
   `prompts/compile_curiosity_folder.md`, and `prompts/dream_entity.md` (tail
   anchor, same EOF pattern as the compile prompts — `auto` → empty → byte-
   identical).
2. In `curiosity/producer.py` and the dream render site, pass
   `output_language_instruction=build_output_language_instruction(CONFIG.personal.output_language)`
   to the respective `render(...)` calls.
3. Mind each prompt's existing structural carve-outs (dream entity pages have
   their own canonical `## State` / `## Timeline` headers — already named in the
   override section, so they stay verbatim).

## Decision gate

Only worth doing if the operator actually wants forced-language curiosity
answers + entity pages. The high-value surface (compiled `knowledge/**`
articles) is already covered. Ask before building.

## Open verification debt (inherited from issue #4)

The live end-to-end — a real SDK compile with `output_language: "de"` on an
English source producing German prose — was never observed. Code path is
verified; LLM-honors-the-instruction is high-confidence-but-untested. Confirm on
the next real compile with the knob set (cheapest: a scratch vault + one English
source file), independent of whether this curiosity/dream extension ships.
