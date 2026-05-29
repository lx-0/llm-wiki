# Relativize-wikilinks — follow-ups

Spun off the 2026-05-29 ad-hoc arc (`AD-HOC-relativize-wikilinks-SUMMARY.md`).
The core fix (links relative-to-file + `wiki links` audit/fixer) shipped; these
are the deliberately-deferred remainders.

## 1. raw/notes/longform/ source-and-final pages not covered (engine gap)
The relativize pass (`run_relativize_pass`) walks `knowledge/` only. Operator-
authored `compile_role: source-and-final` longform docs live under
`raw/notes/longform/` and the engine indexes them but never distills. Their
internal `[[concepts/…]]` links are therefore NOT relativized — and from
`raw/notes/longform/x.md` Obsidian resolves `[[concepts/foo]]` source-relative
(`raw/notes/longform/concepts/foo` ✗) and vault-absolute (`<vault>/concepts/foo`
✗) → the same empty-stub bug the knowledge corpus had.

**Fix:** extend the pass to also cover `raw/notes/longform/` (or any
`compile_role: source-and-final` path). `relativize_text` already works for any
source path — only the walk root is knowledge-scoped. Add a second walk over the
longform dir in `run_relativize_pass` (or generalize its `knowledge_dir` arg to a
list of roots). Re-run the migration CLI with the extended scope. Small.

**Why deferred:** out of the reported scope (knowledge articles), and longform is
a handful of files vs 1.7k articles. Verify with `wiki links` once the pass
covers it (those links currently surface as `raw/…` dangling/embeds).

## 2. 92 missing-article refs (operator content task, not engine)
`wiki links` reports ~92 dangling refs whose target genuinely doesn't exist
(never-created concepts: `concepts/test-driven-development`,
`concepts/verification-before-completion`, `concepts/shape-guards-at-data-boundaries`;
people: `people/timo-fey`, `people/eva`, `people/carina-maehler`; etc.). These
are NOT slug-drift — no rewrite fixes them. Each is either: create the article
(via compile/dream, if the concept is real and recurring), or drop the link.

**Not an engine task.** Could become a `wiki links --fix` extension only if we
add a "stub-create" mode (write a minimal `knowledge/concepts/<slug>.md` for a
chosen missing ref) — but that risks stub-spam and dream-cycle already creates
real pages from substrate. Leave to operator triage via `wiki links`.

## 3. Doc-placeholder links could be escaped (cosmetic)
~11 unresolved links are illustrative examples inside articles about the wiki
(`[[concepts/foo]]`, `[[…]]`, `[[raw/notes/...]]`). They're correctly classified
as placeholders by `wiki links` and ignored by the fixer. Optionally wrap them in
inline code / fences in the source articles so they stop registering as links at
all. Low value; cosmetic.
