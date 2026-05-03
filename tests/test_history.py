"""Tests for utils.append_history + read_history (M003-S05-T01).

Append-only event log at STATE_DIR/history.jsonl. One JSON object per line.
Used by Dashboard P2 charts to render time-series."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_append_history_creates_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import utils

    monkeypatch.setattr(utils, "STATE_DIR", tmp_path)
    utils.append_history("compile", articles_total=5, cost_delta=0.01)

    history_file = tmp_path / "history.jsonl"
    assert history_file.exists()
    line = history_file.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["type"] == "compile"
    assert payload["articles_total"] == 5
    assert payload["cost_delta"] == 0.01
    assert "ts" in payload  # auto-injected


def test_append_history_appends_not_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import utils

    monkeypatch.setattr(utils, "STATE_DIR", tmp_path)
    utils.append_history("compile", articles_total=1)
    utils.append_history("flush", session_id="abc")
    utils.append_history("compile", articles_total=2)

    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    types = [json.loads(line)["type"] for line in lines]
    assert types == ["compile", "flush", "compile"]


def test_read_history_skips_malformed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated or corrupted line must not crash the reader."""
    import utils

    monkeypatch.setattr(utils, "STATE_DIR", tmp_path)
    history_file = tmp_path / "history.jsonl"
    history_file.write_text(
        '{"ts":"2026-05-01T00:00:00Z","type":"compile","articles_total":1}\n'
        'this is not json\n'
        '{"ts":"2026-05-02T00:00:00Z","type":"flush","session_id":"xyz"}\n'
        '\n'  # blank line
        '{truncated\n',
        encoding="utf-8",
    )
    events = utils.read_history()
    assert len(events) == 2
    assert events[0]["type"] == "compile"
    assert events[1]["type"] == "flush"


def test_read_history_returns_empty_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import utils

    monkeypatch.setattr(utils, "STATE_DIR", tmp_path)
    assert utils.read_history() == []
