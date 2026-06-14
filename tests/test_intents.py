"""Intent-dispatch tests — handler registry, workspace/inbox records for
task/idea/note, idempotence, the producer's JSON-parse helpers + confidence
rank. The SDK call itself is not exercised; the deterministic gating + write
paths are."""

from __future__ import annotations

import json

import pytest


def _patch_inbox(monkeypatch, tmp_path):
    """All handlers write via intents._record.WORKSPACE_INBOX_DIR."""
    import intents._record as rec
    monkeypatch.setattr(rec, "WORKSPACE_INBOX_DIR", tmp_path / "workspace" / "inbox")


def test_task_handler_writes_record(tmp_path, monkeypatch):
    _patch_inbox(monkeypatch, tmp_path)
    from intents import dispatch
    from intents.base import Intent

    res = dispatch(Intent(kind="task", summary="Bau einen Collector für Spotify.",
                          source="raw/voice/voice-2026-06-12-2212-x.md", confidence="high"))
    assert res.status == "ok" and res.output and res.output.exists()
    text = res.output.read_text(encoding="utf-8")
    assert "type: task" in text and "status: pending" in text
    assert "source: raw/voice/voice-2026-06-12-2212-x.md" in text
    assert res.output.name == "voice-2026-06-12-2212-x.md"
    assert res.output.parent.name == "inbox"


def test_idea_and_note_handlers(tmp_path, monkeypatch):
    _patch_inbox(monkeypatch, tmp_path)
    from intents import dispatch
    from intents.base import Intent

    idea = dispatch(Intent(kind="idea", summary="Feediverse agents?", source="raw/voice/a.md", confidence="medium"))
    assert idea.status == "ok"
    assert "type: idea" in idea.output.read_text(encoding="utf-8")

    note = dispatch(Intent(kind="note", summary="Gateway lives at llm.yester.cloud", source="raw/voice/b.md", confidence="high"))
    assert note.status == "ok"
    assert "type: note" in note.output.read_text(encoding="utf-8")


def test_handler_idempotent(tmp_path, monkeypatch):
    _patch_inbox(monkeypatch, tmp_path)
    from intents import dispatch
    from intents.base import Intent

    i = Intent(kind="idea", summary="X.", source="raw/voice/n.md", confidence="low")
    assert dispatch(i).status == "ok"
    second = dispatch(i)
    assert second.status == "skipped" and "already exists" in (second.reason or "")


def test_none_is_noop():
    from intents import dispatch
    from intents.base import Intent
    res = dispatch(Intent(kind="none", summary="", source="x.md", confidence="high"))
    assert res.status == "skipped" and res.reason == "no handler"


def test_all_three_handlers_registered():
    from intents.base import get_handler
    assert get_handler("task") is not None
    assert get_handler("idea") is not None
    assert get_handler("note") is not None


def test_producer_registered():
    import producers
    assert "intents" in [p.SPEC.name for p in producers.all_producers()]


def test_strip_json_fences():
    from producers.intents import _strip_json_fences
    assert json.loads(_strip_json_fences('```json\n{"kind": "idea"}\n```')) == {"kind": "idea"}
    assert _strip_json_fences('{"kind": "task"}') == '{"kind": "task"}'


def test_confidence_rank_ordering():
    from producers.intents import _CONFIDENCE_RANK
    assert _CONFIDENCE_RANK["low"] < _CONFIDENCE_RANK["medium"] < _CONFIDENCE_RANK["high"]
