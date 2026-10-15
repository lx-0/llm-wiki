# Report `engine_version` stamps are frozen milestone ids (M034 candidate, surfaced in M033-S04-T06)

**Status:** candidate; small. Recorded 2026-10-15 (M033-S04-T06).

**Today:** four writers stamp a hard-coded milestone id into report frontmatter as
`engine_version`: `reports/_engine/runner._report_frontmatter` → `M019-S02-T04` (every
per-instrument report), `reports/_engine/lib/render_summary._frontmatter_lines` →
`M019-S04` (the meta-report `_summary.md`), `reports/_engine/lib/analyst.py` (two sites) →
`M019-S05` (the Pass-1 analyses). The repo-wide consumer grep (`scripts/ templates/ docs/
tests/ desktop/src prompts/`) finds no reader. The T06 split moved the two report writers
verbatim.

**Why it matters:** the field claims provenance it does not carry — a report written today
by the M033 engine says M019. The embedded-methodology posture (a future reader must be able
to interpret a report without the engine) depends on honest provenance; `prompt_version`
(the hash of the prompt actually sent) is honest, `engine_version` is not.

**Proposal:** one helper returning the engine's real version (the `pyproject.toml` version
plus the short SHA of the engine checkout, with a fallback when git is unavailable), used by
all four writers; a test that every writer stamps the helper's value and no literal
milestone id remains; old reports keep their stamp (no rewrite). The field's fate is the
decision to make first — recommendation: keep it and make it honest, it is the only
engine-side provenance a report carries.
