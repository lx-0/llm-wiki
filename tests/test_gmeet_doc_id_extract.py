"""Tests for `gmeet.extract_drive_doc_ids` — the pure doc-url → id extractor
used by email-discovery to pull the linked Doc out of a Gemini-notes mail."""

from __future__ import annotations

from collectors import gmeet


def test_no_links_returns_empty() -> None:
    assert gmeet.extract_drive_doc_ids("no links here at all") == []
    assert gmeet.extract_drive_doc_ids("") == []
    assert gmeet.extract_drive_doc_ids(None) == []  # type: ignore[arg-type]


def test_single_link_edit_suffix() -> None:
    blob = (
        '<a href="https://docs.google.com/document/d/'
        '1G6nzuLfuVZPL9i8jZqousjbeKuG2gR9aSB7kEIPZZPA/edit?usp=meet_tnfm_email">open</a>'
    )
    assert gmeet.extract_drive_doc_ids(blob) == ["1G6nzuLfuVZPL9i8jZqousjbeKuG2gR9aSB7kEIPZZPA"]


def test_multiple_links_dedup_order_preserving() -> None:
    blob = (
        "see https://docs.google.com/document/d/AAA111/edit and "
        "https://docs.google.com/document/d/BBB222/view and again "
        "https://docs.google.com/document/d/AAA111/edit?usp=drivesdk"
    )
    assert gmeet.extract_drive_doc_ids(blob) == ["AAA111", "BBB222"]


def test_ids_with_underscore_and_dash() -> None:
    blob = "https://docs.google.com/document/d/1d5eWN-Ph_tVnHt/edit"
    assert gmeet.extract_drive_doc_ids(blob) == ["1d5eWN-Ph_tVnHt"]


def test_multiline_html_blob() -> None:
    blob = (
        "<html>\n<body>\n"
        '  <a href="https://docs.google.com/document/d/1wWh2GVj_y/edit">Notes</a>\n'
        "</body>\n</html>\n"
    )
    assert gmeet.extract_drive_doc_ids(blob) == ["1wWh2GVj_y"]
