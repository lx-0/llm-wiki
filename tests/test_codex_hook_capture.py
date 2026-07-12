"""Turn identity behavior for the shared session-end hook."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_session_end_module():
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "session-end.py"
    spec = importlib.util.spec_from_file_location("wiki_session_end", hook_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_stop_uses_turn_id_as_capture_id():
    module = _load_session_end_module()

    capture_id = module.capture_id_for_hook(
        {
            "hook_event_name": "Stop",
            "session_id": "11111111-1111-1111-1111-111111111111",
            "turn_id": "22222222-2222-2222-2222-222222222222",
        }
    )

    assert capture_id == "22222222-2222-2222-2222-222222222222"


def test_claude_session_end_keeps_session_id_as_capture_id():
    module = _load_session_end_module()

    capture_id = module.capture_id_for_hook(
        {
            "hook_event_name": "SessionEnd",
            "session_id": "11111111-1111-1111-1111-111111111111",
        }
    )

    assert capture_id == "11111111-1111-1111-1111-111111111111"


def test_missing_codex_turn_id_falls_back_to_session_id():
    module = _load_session_end_module()

    capture_id = module.capture_id_for_hook(
        {
            "hook_event_name": "Stop",
            "session_id": "11111111-1111-1111-1111-111111111111",
        }
    )

    assert capture_id == "11111111-1111-1111-1111-111111111111"
