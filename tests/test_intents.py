"""Intent-dispatch tests — handler registry, task record, idempotence,
confidence floor, and the producer's JSON-parse helpers. The SDK call itself
is not exercised (no network); the deterministic gating + write paths are."""

from __future__ import annotations

import json

import pytest


def test_task_handler_writes_record(tmp_path, monkeypatch):
    import intents.task_handler as th
    from intents import dispatch
    from intents.base import Intent

    monkeypatch.setattr(th, "TASKS_DIR", tmp_path / "tasks")

    intent = Intent(
        kind="task",
        summary="Bau einen Collector für Spotify.",
        source="raw/voice/voice-2026-06-12-2212-x.md",
        confidence="high",
    )
    res = dispatch(intent)
    assert res.status == "ok"
    assert res.output is not None and res.output.exists()
    text = res.output.read_text(encoding="utf-8")
    assert "status: pending" in text
    assert "source: raw/voice/voice-2026-06-12-2212-x.md" in text
    assert "Bau einen Collector für Spotify." in text
    # filename derives from source stem (stable → idempotent)
    assert res.output.name == "voice-2026-06-12-2212-x.md"


def test_task_handler_idempotent(tmp_path, monkeypatch):
    import intents.task_handler as th
    from intents import dispatch
    from intents.base import Intent

    monkeypatch.setattr(th, "TASKS_DIR", tmp_path / "tasks")
    intent = Intent(kind="task", summary="X.", source="raw/voice/n.md", confidence="high")
    assert dispatch(intent).status == "ok"
    second = dispatch(intent)
    assert second.status == "skipped"
    assert "already exists" in (second.reason or "")


def test_dispatch_none_is_noop():
    from intents import dispatch
    from intents.base import Intent

    res = dispatch(Intent(kind="none", summary="", source="x.md", confidence="low"))
    assert res.status == "skipped"
    assert res.reason == "no handler"


def test_unknown_kind_is_noop():
    from intents import dispatch
    from intents.base import Intent

    res = dispatch(Intent(kind="research", summary="...", source="x.md", confidence="high"))
    assert res.status == "skipped"  # handler not built yet → forward-compatible no-op


def test_registry_rejects_duplicate_kind():
    from intents.base import register

    with pytest.raises(ValueError, match="already registered"):

        @register
        class DupTask:
            KIND = "task"

            def handle(self, intent):  # pragma: no cover
                ...


def test_producer_registered():
    import producers

    assert "intents" in [p.SPEC.name for p in producers.all_producers()]


def test_strip_json_fences():
    from producers.intents import _strip_json_fences

    fenced = '```json\n{"kind": "none"}\n```'
    assert json.loads(_strip_json_fences(fenced)) == {"kind": "none"}
    plain = '{"kind": "task"}'
    assert _strip_json_fences(plain) == plain


def test_seen_guard_roundtrip(tmp_path, monkeypatch):
    import producers.intents as pi

    monkeypatch.setattr(pi, "STATE_DIR", tmp_path)
    monkeypatch.setattr(pi, "_SEEN_STATE", tmp_path / "intents-seen.json")
    assert pi._load_seen() == set()
    pi._mark_seen("raw/voice/a.md")
    pi._mark_seen("raw/voice/b.md")
    assert pi._load_seen() == {"raw/voice/a.md", "raw/voice/b.md"}


def test_confidence_rank_ordering():
    from producers.intents import _CONFIDENCE_RANK

    assert _CONFIDENCE_RANK["low"] < _CONFIDENCE_RANK["medium"] < _CONFIDENCE_RANK["high"]
