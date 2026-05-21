---
milestone: M024
slice: S01
status: done
commit: f35cce0
---

# M024-S01 — SUMMARY

Foundations, all unit-tested, no collector wiring.

- **T01 export UTF-8 fix** — `_DriveClient._get` pins `r.encoding="utf-8"` on the
  non-JSON branch. Drive's charset-less `text/markdown` was Latin-1-decoded
  (`Ã¤` for `ä`), corrupting every German transcript (incl. the operator's own).
- **T02 doc-id extractor** — `extract_drive_doc_ids(text)`: order-preserving,
  deduped regex over `docs.google.com/document/d/<id>`.
- **T03 reader HTML body** — `ThunderbirdMboxReader._extract_body` now returns
  `(text, html)` and populates `Message.body_html`. Live-probe proved the
  gemini-notes Drive link lives ONLY in the text/html alternative (plaintext
  drops it) — so without this the extractor would always find nothing.

Tests: 9 new (`test_gmeet_export_encoding`, `test_gmeet_doc_id_extract`,
`test_thunderbird_html_body`). 74 related green, no regressions. imap.py has its
own `_extract_body` (untouched); no imap account carries a gmeet block.
