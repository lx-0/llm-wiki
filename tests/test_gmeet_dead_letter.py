"""gmeet export dead-letter (M031-S03, backlog gmeet-export-dead-letter.md).

Un-exportable Drive doc-ids (access revoked / deleted) were re-attempted on
every run — 8 warning blocks in 30 days for the same ids, one id failing
across runs with no skip. Negative cache per account with bounded re-probe.
"""
from __future__ import annotations

from collectors.gmeet import _dead_letter_skip, _record_export_failure

NOW = "2026-08-26T10:00:00+02:00"


def test_records_failure_with_attempt_count() -> None:
    dead: dict = {}
    _record_export_failure(dead, "doc1", "unexpected 404 on GET …", now=NOW)
    _record_export_failure(dead, "doc1", "unexpected 404 on GET …", now=NOW)
    entry = dead["doc1"]
    assert entry["attempts"] == 2
    assert entry["first_seen"] == NOW and entry["last_attempt"] == NOW
    assert "404" in entry["last_error"]


def test_skip_only_after_attempt_budget() -> None:
    dead: dict = {}
    for _ in range(2):
        _record_export_failure(dead, "doc1", "404", now=NOW)
    assert _dead_letter_skip(dead.get("doc1"), now=NOW, max_attempts=3, reprobe_days=7) is False
    _record_export_failure(dead, "doc1", "404", now=NOW)
    assert _dead_letter_skip(dead.get("doc1"), now=NOW, max_attempts=3, reprobe_days=7) is True


def test_reprobe_after_cadence_allows_retry() -> None:
    dead: dict = {}
    for _ in range(3):
        _record_export_failure(dead, "doc1", "404", now="2026-08-01T10:00:00+02:00")
    # within the 7-day window → skip; after it → re-probe (a re-granted doc
    # must eventually import again)
    assert _dead_letter_skip(dead["doc1"], now="2026-08-05T10:00:00+02:00",
                             max_attempts=3, reprobe_days=7) is True
    assert _dead_letter_skip(dead["doc1"], now="2026-08-26T10:00:00+02:00",
                             max_attempts=3, reprobe_days=7) is False


def test_none_entry_never_skips() -> None:
    assert _dead_letter_skip(None, now=NOW, max_attempts=3, reprobe_days=7) is False
