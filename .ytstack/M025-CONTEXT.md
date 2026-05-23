---
milestone: M025
project: llm-wiki
created: 2026-05-23T08:42:54+0200
size: M
---

# M025 -- Context

## Goal

An operator can see how the brain interpreted each cryptic quick-capture and
overturn a wrong reading by capture-ID; the brain marks the old interpretation
superseded and regenerates the affected article on its next compile cycle.

## Exit criteria

- A capture dropped via the capture door lands in `raw/` with a stable capture-ID
  in frontmatter, and that ID survives into the compiled artifact's `compiled_from`.
- The `daily-digest` shows recent captures keyed by ID, with the interpretation +
  the context the brain added.
- A capture line referencing a known ID is recognized as a correction and writes a
  supersede-marker against that capture's interpretation.
- End-to-end: a wrong reading, corrected by ID, yields a corrected article after one
  normal compile cycle (no manual recompile, no instant surgical patch).
- Scope guard: no instant single-item surgical-patch primitive is introduced.

## Size

M -- see `M025-ROADMAP.md` for slice breakdown. 3 slices.

## Source

Validated pitch: `.ytstack/OFFICE-HOURS-capture-correction-loop.md`
(office-hours: two premise-challenge rounds; plan-ceo-review: REDUCTION -> B-minus).

## Decisions locked in discuss phase

- 2026-05-23: Capture door is NOT the feature -- reuse the existing file-drop
  (`inbox`/`voice`) substrate. The pitch is the correction loop only. (office-hours,
  operator-confirmed: single-stream capture is trivially file-based.)
- 2026-05-23: `reconcile` cannot carry the correction loop -- it is
  fact-violation-only and never fires for free-text corrections. The loop needs its
  own ID + supersede primitive. (office-hours premise-challenge 2.)
- 2026-05-23: SCOPE REDUCTION -> B-minus. Drop the targeted instant single-item
  downstream patch (the M018 / `commit_article` agent-side-write re-architecture
  risk). Replace with a supersede-marker honoured by the next normal compile cycle.
  Async fix is sufficient -- operator corrects async (digest) anyway, and the
  ID-keyed supersede-marker is the substrate-agnostic primitive that generalizes
  toward the 12-month "all interpretations correctable + brain learns priors" ideal.
  (plan-ceo-review.)

## Out of scope (follow-up, do not sneak back in)

- Targeted instant single-item patch -- only if async proves too slow in practice.
- Confidence-gated proactive push (pitch alternative C) -- after data on correction
  frequency.
- Correction-priors learning (the 12-month cathedral) -- after the loop is used.
- Generalizing the back-channel beyond captures to all substrates -- trajectory.

## Open questions

- Item 5 seam (resolve before/during slicing): does `compile` have a clean
  "regenerate the article(s) derived from capture-ID X" path, or only full-corpus /
  per-source-file compiles? The supersede-marker -> affected-article link is the
  thing to nail down. If compile is per-source-file, "superseded capture ->
  re-compile that source" is natural.
- Capture surface concretely: ID-prefixed line in an append-only note vs discrete
  file drop -- which one-tap door does Sidney actually use? (Not load-bearing for
  the loop; the ID + supersede mechanics are surface-agnostic.)
