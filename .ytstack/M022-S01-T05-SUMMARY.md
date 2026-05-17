---
milestone: M022
slice: S01
task: T05
project: llm-wiki
closed: 2026-05-17T14:05:00Z
verification: passed
---

# M022-S01-T05 — Summary

## Outcome

Four pytest cases added to `tests/test_inbox_and_html.py` under section `## process_inbox two-zone routing (M022-S01-T05)`:

- `test_process_inbox_md_writes_artifact_and_archives_original` — md drop → artifact in `raw/notes/` (has frontmatter) + original in `raw/inbox-wiki/` (byte-identical to input).
- `test_process_inbox_html_archives_original_not_unlinked` — html drop → original in `raw/inbox-wiki/` (regression-guard against the legacy `unlink()` path).
- `test_process_inbox_mp3_archives_only_no_artifact` — mp3 drop → archive-only, `classify_file` never invoked, no entries under `raw/notes/`.
- `test_process_inbox_pdf_archives_only_no_artifact` — same shape for pdf.

Shared helper `_isolated_inbox(tmp_path, mod)` redirects every path constant in the loaded `process-inbox` module to a tmp_path subtree (mirrors the T02 smoke-probe pattern, now reusable).

## Deviations from plan

None. Verification command matched expected output (4 selected tests passed; full suite 828/828).

## Follow-ups

- Test coverage focuses on the post-T02 two-zone invariants. NOT covered:
  - Filename-collision branch in `_archive_to_inbox_wiki()` (mtime-iso suffix path) — adds value if/when a real collision surfaces; defer until then.
  - ingest-html.py end-to-end (still mocked via `subprocess.run`). End-to-end LLM coverage stays out of unit tests by project convention.
  - dry-run path output strings — current tests only exercise `dry_run=False`.

## Verification

- `uv run --project .wiki pytest tests/test_inbox_and_html.py -v -k "two_zone or archives or md_writes"` → 4 passed, 14 deselected.
- `uv run --project .wiki pytest -q` → 828/828 passed.
- Commit: `330f9f7`.
