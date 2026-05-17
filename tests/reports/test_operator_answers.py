"""Tests for the M019-S05+ operator-input mechanism — _load_operator_answers."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.reports._engine.runner import _load_operator_answers


def test_returns_empty_when_no_study_dir() -> None:
    assert _load_operator_answers(None, "phq-9") == {}


def test_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert _load_operator_answers(tmp_path, "phq-9") == {}


def test_loads_one_instrument_one_item(tmp_path: Path) -> None:
    (tmp_path / "operator_answers.yaml").write_text(
        yaml.safe_dump({
            "phq-9": {
                "9": {"value": 0, "answered_at": "2026-05-17T16:00:00+00:00"},
            },
        }),
        encoding="utf-8",
    )
    result = _load_operator_answers(tmp_path, "phq-9")
    assert result == {"9": 0}


def test_loads_multiple_items(tmp_path: Path) -> None:
    (tmp_path / "operator_answers.yaml").write_text(
        yaml.safe_dump({
            "phq-9": {
                "2": {"value": 1},
                "5": {"value": 0},
                "9": {"value": 0, "note": "stable"},
            },
        }),
        encoding="utf-8",
    )
    result = _load_operator_answers(tmp_path, "phq-9")
    assert result == {"2": 1, "5": 0, "9": 0}


def test_filters_to_requested_instrument(tmp_path: Path) -> None:
    """Different instrument's answers are ignored."""
    (tmp_path / "operator_answers.yaml").write_text(
        yaml.safe_dump({
            "phq-9": {"9": {"value": 0}},
            "gad-7": {"2": {"value": 1}},
        }),
        encoding="utf-8",
    )
    assert _load_operator_answers(tmp_path, "phq-9") == {"9": 0}
    assert _load_operator_answers(tmp_path, "gad-7") == {"2": 1}
    assert _load_operator_answers(tmp_path, "asrs-v1.1") == {}


def test_skips_malformed_entries(tmp_path: Path) -> None:
    """Entries without 'value' or non-int values are silently dropped."""
    (tmp_path / "operator_answers.yaml").write_text(
        yaml.safe_dump({
            "phq-9": {
                "1": {"value": 2},
                "2": {"note": "no value here"},
                "3": {"value": "not-an-int"},
                "4": "raw-string-not-dict",
            },
        }),
        encoding="utf-8",
    )
    result = _load_operator_answers(tmp_path, "phq-9")
    assert result == {"1": 2}
