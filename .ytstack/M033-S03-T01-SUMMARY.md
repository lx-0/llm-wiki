---
milestone: M033
slice: S03
task: T01
project: llm-wiki
closed: 2026-10-14T21:31:55+02:00
verification: passed
---

# M033-S03-T01 -- Summary

## Commits

`f03d13b` — the fold, the parity test module, the dream-sampling test on the seam; this
summary, the slice-plan flip and STATE follow under the same ref
(`git log --grep '^M033-S03-T01'`). Planning commit `c658599`.

## Outcome

Nine private frontmatter grammars in the top-level scripts are gone; the ten scripts (the
plan's nine plus `cleanup_legacy_daily_roots.py`) read through `core/frontmatter`. `pin`,
`web_research`, `dedup` (3 sites), `health_trends`, `reconcile`, `dream` (5 sites) call
`frontmatter.parse`; the four `import yaml` lines that served only a copy went with them.
Two call-site contracts were kept on purpose through `parse_strict` + `except
FrontmatterError`: the picture-sidecar backfill still answers `skipped:no_frontmatter` for
a malformed block instead of half-reading it, and the daily-rollup backfill still logs the
file path on a malformed block (`split_fence` first, so a fence-less file stays silent as
before). `_scalar_fm` and the two private `_FRONTMATTER_RE`s became `frontmatter.field` /
`split_fence`; the digest predicate in `cleanup_legacy_daily_roots` is
`field(text, "type") == "daily-digest"`. `lint.py` was already on the seam (C03).
Repo-wide `def …frontmatter…(` count 31 → 26; in the ten scripts only read-wrappers remain
(`pin`, `reconcile`, `backfill_daily_rollup`, `lint` — read a file, call the seam) plus the
predicate.

Parity evidence, run before the fold (`/tmp/t01-parity.py`, 13 shapes × 11 helpers): 119 of
143 comparisons identical; the 24 differences are exactly the seam's tolerance — CRLF text,
a closing fence at EOF without newline, trailing spaces on a fence line (the copies answered
"no frontmatter" there) — plus two decisions: `pin` now drops a trailing `# comment` from a
scalar (the YAML comment rule) and the digest predicate accepts `type: "daily-digest"`
(quotes are YAML, not the value) and matches exactly instead of the old `\b` prefix.
File-reading sites see no CRLF delta at all — `read_text` normalises newlines — which is
why four of the planned delta cases passed before the fold and stay as contract pins.

Guards: `tests/test_frontmatter_parity.py` (14 cases; six RED before the fold: the pin
wrapper, quoted / CRLF / exact-match digest detection, fence-at-EOF in the rollup and
reconcile readers); `tests/test_dream_sampling.py` reads through the seam;
`tests/test_errors.py`'s warning contract unchanged.

## Deviations from plan

- A tenth site (`cleanup_legacy_daily_roots.py`) joined — found by the repo-wide grep while
  planning.
- The delta cases for file-reading sites (rollup meetings / voice, health metrics, dedup
  entity page) were not RED: `read_text` had already normalised CRLF for the old copies.
  Kept as pins; the fence-at-EOF cases carried the RED instead.
- `contextlib.suppress` for the meetings title read (ruff SIM105 on the first version).

## Follow-ups

- T02 inherits the extra reader sites listed in the S03 notes
  (`compile_stages/classify._frontmatter_type`, `core/utils._parse_fact_frontmatter`,
  `reports/_engine/lib/verify_report._extract_frontmatter`,
  `core/links._strip_frontmatter_and_fences`, the test-local helper in
  `tests/reports/test_runner_report.py`).

## Verification

Plan command 1 → 131 passed (targeted set), `uv run pytest -q` → **2071 passed, 1 skipped**,
`ruff check` → `All checks passed!`, `ruff format --check` → 392 files already formatted.
Plan command 2 (the grep over the ten scripts) → `pin._read_frontmatter`,
`reconcile._read_frontmatter`, `backfill_daily_rollup._read_frontmatter`,
`cleanup_legacy_daily_roots._has_digest_frontmatter`, `lint._read_frontmatter` — all
read-wrappers or the predicate on the seam, no grammar left. Oracle green inside the suite.
CI on `origin/main`: recorded in STATE.
