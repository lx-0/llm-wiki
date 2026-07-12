"""Transcript normalization across Claude Code and Codex rollout JSONL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from _transcript import build_context, read_transcript  # noqa: E402


TARGET_TURN = "22222222-2222-2222-2222-222222222222"
NEXT_TURN = "33333333-3333-3333-3333-333333333333"


def _write_jsonl(path: Path, entries: list[dict], *, malformed: bool = False) -> None:
    lines = [json.dumps(entry) for entry in entries]
    if malformed:
        lines.insert(2, "{not-json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _message(role: str, block_type: str, text: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": block_type, "text": text}],
        },
    }


def test_codex_reader_isolates_requested_turn_and_ignores_injected_context(tmp_path: Path):
    transcript = tmp_path / "rollout.jsonl"
    _write_jsonl(
        transcript,
        [
            _message("user", "input_text", "AGENTS payload that must stay out"),
            {"type": "turn_context", "payload": {"turn_id": TARGET_TURN}},
            _message("user", "input_text", "Implement Codex capture"),
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "call-1",
                    "input": json.dumps({"cmd": "pytest -q"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-1",
                    "output": "3 passed",
                },
            },
            _message("assistant", "output_text", "Implemented and verified"),
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TARGET_TURN}},
            {"type": "turn_context", "payload": {"turn_id": NEXT_TURN}},
            _message("user", "input_text", "This belongs to the next turn"),
        ],
        malformed=True,
    )

    turns = read_transcript(str(transcript), turn_id=TARGET_TURN)

    assert [(turn.role, turn.text) for turn in turns if turn.text] == [
        ("user", "Implement Codex capture"),
        ("assistant", "Implemented and verified"),
    ]
    context = build_context(turns)
    assert "[exec]" in context
    assert "3 passed" in context
    assert "AGENTS payload" not in context
    assert "next turn" not in context


def test_codex_reader_defaults_to_latest_turn(tmp_path: Path):
    transcript = tmp_path / "rollout.jsonl"
    _write_jsonl(
        transcript,
        [
            {"type": "turn_context", "payload": {"turn_id": TARGET_TURN}},
            _message("user", "input_text", "Older turn"),
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TARGET_TURN}},
            {"type": "turn_context", "payload": {"turn_id": NEXT_TURN}},
            _message("user", "input_text", "Latest turn"),
            _message("assistant", "output_text", "Latest answer"),
        ],
    )

    context = build_context(read_transcript(str(transcript)))

    assert "Latest turn" in context
    assert "Latest answer" in context
    assert "Older turn" not in context


def test_claude_reader_remains_compatible(tmp_path: Path):
    transcript = tmp_path / "claude.jsonl"
    _write_jsonl(
        transcript,
        [
            {"message": {"role": "user", "content": "Claude question"}},
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Claude answer"}],
                }
            },
        ],
    )

    turns = read_transcript(str(transcript), turn_id=TARGET_TURN)

    assert [(turn.role, turn.text) for turn in turns] == [
        ("user", "Claude question"),
        ("assistant", "Claude answer"),
    ]
