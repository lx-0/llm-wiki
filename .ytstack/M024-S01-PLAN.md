---
milestone: M024
slice: S01
status: planned
created: 2026-05-21
---

# M024-S01 — Foundations: UTF-8 export fix · doc-id extractor · reader HTML body

Pure/low-risk building blocks, all unit-tested. No collector wiring yet.

## Tasks

- [ ] T01 — `export_doc` UTF-8 fix
  - `scripts/collectors/gmeet.py` `_DriveClient._get`: the `expect_json=False`
    branch returns `r.text`, which decodes Google's charset-less `text/markdown`
    as Latin-1 (`Ã¤` for `ä`). Set `r.encoding = "utf-8"` before `.text`.
  - Test: `tests/test_gmeet_export_encoding.py` — a fake response with UTF-8
    bytes + no charset; assert decoded text has `ä`/`🚀`, not mojibake.

- [ ] T02 — Drive doc-id extractor (pure)
  - New `extract_drive_doc_ids(text: str) -> list[str]` in `gmeet.py`:
    regex `docs\.google\.com/document/d/([A-Za-z0-9_-]+)`, order-preserving,
    deduped. Module-level compiled `_DOC_URL_RE`.
  - Test: `tests/test_gmeet_doc_id_extract.py` — 0 links, 1 link, N links
    (dedup), real `?usp=meet_tnfm_email` / `/edit` suffixes, multiline HTML blob.

- [ ] T03 — Thunderbird reader populates `body_html`
  - `scripts/adapters/mailbox/thunderbird.py` `_extract_body`: currently returns
    only the `text/plain` part. Return `(text, html)`; populate
    `Message.body_html`. Handle multipart/alternative + singlepart text/html.
  - Test: `tests/test_thunderbird_html_body.py` — multipart/alternative fixture
    (text/plain + text/html) → both populated; plain-only → html None.

## Verification

`uv run --project .wiki pytest tests/test_gmeet_export_encoding.py tests/test_gmeet_doc_id_extract.py tests/test_thunderbird_html_body.py -q`
