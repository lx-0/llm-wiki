---
milestone: M025
slice: S02
task: T03
project: llm-wiki
closed: 2026-06-25
verification: passed
---

# M025-S02-T03 — Summary

## Outcome

Correction *recognition* (capture-side; the supersede write-back is S03):

- `core/capture_index.detect_correction(content, *, known_ids) -> str | None` — if a
  capture body opens with `re:<id>` / `corrects:<id>` (`:` or `#` separator) referencing
  a **known** capture id, returns the full id it corrects; else None. The reference may
  be the digest short-id (a 6–12 hex prefix) or the full id, and resolves only when it
  *uniquely* prefixes one known id. The hex shape + known-id check keep an ordinary
  `Re: <subject>` email snippet from false-matching; an unknown id falls back to a fresh
  capture.
- `collectors/capture_collector.py` snapshots known ids once per run, calls
  `detect_correction` per capture, and stamps `kind: correction` + `corrects: <full-id>`
  into the frontmatter when it fires (fresh captures are unchanged).
- `docs/setup-captures.md` — operator recipe: inbox path, `config.yaml` wiring, the
  digest `## Captures` forward-link, and the `corrects:<id>` / `re:<id>` correction
  syntax. Honestly scoped: it states the supersede + auto-regeneration is M025-S03.

## Deviations from plan

- None structural. Detection lives in `capture_index` (the correction-loop module) and
  is called by the collector — keeps the regex/known-id logic unit-testable apart from
  the collector's file I/O.
- Intra-batch corrections (a capture correcting another dropped in the *same* run) are
  not supported — known-ids are snapshotted once at run start. Acceptable: corrections
  are async by design (M025 decision — operator corrects after seeing the digest).

## Verification

`uv run --project .wiki pytest tests/test_capture_index.py tests/test_capture_collector.py`
— 39 passed (7 new `detect_correction` unit tests: full-id / short-prefix / corrects+#
forms / unknown-id-is-fresh / no-leading-token / ordinary-email-Re / ambiguous-prefix;
3 new collector integration tests: tagged-when-known / fresh-has-none / unknown-is-fresh).
Full suite: **1407 passed, 1 skipped**.

## Slice close

**S02 complete (3/3).** The loop is observable + corrections are recognised. S03 carries
the write-back: a `capture_index.update_status()` supersede primitive honoured by the
next compile cycle (regenerates the affected article), end-to-end — and carries the open
compile-regeneration eng-seam flagged in the roadmap.
