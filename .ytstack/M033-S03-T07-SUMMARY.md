---
milestone: M033
slice: S03
task: T07
project: llm-wiki
closed: 2026-10-15T01:36:00+02:00
verification: passed
---

# M033-S03-T07 -- Summary

## Commits

`167c3c6` — the fold (eight sites, the widened guard). Planning commit `214e001`. This
summary, the slice-plan flip and STATE follow under the same ref
(`git log --grep '^M033-S03-T07'`).

## Outcome

One fence grammar everywhere. The eight readers that still carried their own opening /
closing-fence rule — a regex (`_FRONTMATTER_RE` in health, daily_capture and the type
migration, `_FM_RE` in capture_index), a `startswith("---")` / `find("\n---")` pair (two
calendar probes, the word count, the final-only probe) or a strip of the first `---` line
(the suggestion loader) — read through `core.frontmatter`: `split_fence` for the split
(calendar's operator-prose split, capture_index's gist, daily_capture's `sources:` reader,
the word count, the type migration's fence question and rewrite), `parse` where a bad block
means "skip" (calendar's transcript scan, `_compiled_from`), `parse_strict` where it must be
heard (health's merge keeps its WARNING and rebuilds; a suggestion file raises as it did),
`field` for one scalar (`compile_role`, `type` — quotes and trailing comments handled by
the seam). The hand-parsed `sources:` list in daily_capture, the in-block `type:` replace /
after-`title:` insert in the migration and every writer stay — they are not read grammars.
Five unused imports (`re` ×3, `yaml` ×2) went with the grammars.

The guard `tests/test_frontmatter_parity.py::test_no_fence_grammar_anywhere_outside_the_seam`
scans every line of every module under `scripts/` for the fence-read smells (`\A---`,
`"^---`, `startswith("---`, `find("\n---`, the private regex names) — RED on 18 lines in 8
modules before the fold, green after; `lint.py` is allow-listed with its reason (`^---\s*$`
over the BODY finds thematic breaks before `## Timeline`). T02's function-level guard stays.
Exit criterion 5 ("0 private frontmatter parsers") is measured by this guard from now on.

Parity on the operator vault (read-only, `/tmp/t07-parity.py` → `/tmp/t07-diff.py`): word
counts, `_is_final_only`, `_compiled_from`, `needs_migration` + `apply_migration` over 2273
articles, `_split_operator_prose` over 191 calendar notes, `_scan_transcripts` (38 refs),
`_read_sources_and_body` over 686 daily files, `load_suggestion` over 15 files — 0 deltas
between `afd1649` and `167c3c6`. The seam's tolerance differs from the old grammars only on
inputs the vault does not contain (a `----` line closing a fence, a `---` inside a value
cutting the word count, a fence at EOF without a newline wrapping a second fence in the
migration, a `# comment` after `final-only`, an empty block in a health file now warning).

## Deviations from plan

- The guard's smell list dropped `r"^---` as a separate entry — `'"^---'` matches both
  spellings.
- `dashboard_stats` carried a second, function-local `import re` that the module-level one
  masked (ruff F811 once the probe went); the module-level import is gone.

## Follow-ups

- None for the seam. The write side (the hand-built `sources:` / voice / capture / inbox
  writers vs `frontmatter.serialize`) remains the recorded shape decision from T02.

## Verification

Plan command 1 → targeted set `179 passed`; `uv run pytest -q` → **2117 passed, 1 skipped**
(+1: the widened guard); `ruff check` → `All checks passed!`; `ruff format --check scripts
hooks tests` → clean (health.py formatted by explicit path). Plan command 2 (the grep) →
empty. Plan command 3 → `TOTAL DELTAS 0`. CI: `214e001` green; `167c3c6` recorded in STATE.
