---
milestone: M033
slice: S03
task: T03
project: llm-wiki
closed: 2026-10-14T21:55:39+02:00
verification: passed
---

# M033-S03-T03 -- Summary

## Commits

`452d9ae` — the four collector copies onto `core/utils.slugify(…, ascii_only=True)`;
`4773bf2` — the three copies the audit missed (health, curiosity ×2), the `empty=` keyword,
the second-grammar guard, T07 added to the slice plan. This summary, the slice-plan flip and
STATE follow under the same ref (`git log --grep '^M033-S03-T03'`). Planning commit `56c9cdb`.

## Outcome

One slug function. `core/utils.slugify(text, max_len=None, *, ascii_only=False, empty=None)`
carries both grammars the engine's filenames depend on, selected explicitly: the default
(Unicode word characters survive, punctuation dropped, a plain cut) names `knowledge/facts/`,
`knowledge/takes/`, voice notes and html ingests; `ascii_only=True` (every run of
non-`[a-z0-9]` → `-`, a cut never ends in `-`, empty → `"untitled"`) is the grammar behind
every jamie / gmeet / calendar / youtube filename and was four byte-identical private copies
plus two inline `re.sub` lines in `curiosity/producer.py` plus `health._slug_account`
(`empty="account"`). Merging the two grammars was not an option — the collectors would rename
every new transcript with an umlaut or apostrophe (`m-glich` → `möglich`), the default would
orphan facts and takes whose slug is their identity — so the fold is one implementation with
the second grammar as a keyword, both pinned by `tests/test_slugify.py` on the shapes behind
real filenames. `publish/corpus.server_slug` stays: an exact port of context-mcp's
`slugifySkillName` (NFKD fold, diacritics stripped) — the server's grammar, pinned as a
fixpoint, allow-listed in the guard by reason. Seven call sites spell
`slugify(x, max_len=60|50|40, ascii_only=True)`; `def _?slugify(` 5 → 1 repo-wide,
`[^a-z0-9]+` grammars outside the seam 4 → 1 (the server port).

Evidence on the operator vault (read-only, `/tmp/t03-evidence.py`): the slug segment of
every real collector filename recomputed from the file's own `title:` / `channel:` with the
unified function — jamie 27 / 27, gmeet 11 / 11, youtube 3 / 3 match, 0 mismatches.

Guards: `tests/test_slugify.py` — both grammars (RED first: the keyword did not exist, nine
cases), the `empty` fallback, the request-slug shape, and
`test_no_second_slug_grammar_outside_the_seam` (RED on `health.py:66`,
`producer.py:492`, `producer.py:799`; green after). `tests/test_calendar_collector.py` on the
seam.

## Deviations from plan

- The audit's "5" was a def-name count; the smell grep (`[^a-z0-9]+`) found three more
  copies and one legitimate non-copy (the server port). Folded in a second commit.
- `curiosity` request slugs: strip-then-cut instead of cut-then-strip, and `"untitled"`
  instead of `""` for an all-punctuation topic — recorded; requests are transient
  `raw/requests/*.json`, no existing file changes.
- The `empty` keyword was written before its test (a three-line change); the guard carried
  the RED for that commit. Noted, not repeated.
- The same smell approach applied to frontmatter found eight private fence grammars under
  functions T02's name-based guard never looked at → **T07** added (slice at its maximum of
  seven tasks); exit criterion 5 is measured by the widened guard T07 builds.

## Follow-ups

- T07: the eight unnamed fence grammars + the widened guard (see the slice plan).
- KNOWLEDGE: name-based guards and def-name audits undercount — scan by smell, allow-list by
  reason.

## Verification

Plan command 1 (targeted set) → 88 passed (first commit) / suite; `uv run pytest -q` →
**2091 passed, 1 skipped**; `ruff check` → `All checks passed!`; `ruff format --check` →
clean after one reformat each commit. Plan command 2 (`grep -rnE 'def _?slugify\(|_SLUG_RE'
scripts`) → `core/utils.py` only (`_ASCII_SLUG_RE` + the def). Real-vault recomputation:
41 / 41. CI: `452d9ae` green (runs 38626966467 + 38626966454); `4773bf2` recorded in STATE.
