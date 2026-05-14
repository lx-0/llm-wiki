"""Smoke test for the summarize-day agent task (M004-S02).

The Claude Agent SDK is mocked so the test runs offline. The mock pretends to
be the agent and yields a single ResultMessage — verifying the wiring (spec
resolution, body rendering, log persistence, last_run frontmatter update)
without requiring a real LLM.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.agent_spec import parse_spec


AGENT_SPECS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "agents"


def test_summarize_day_spec_loads() -> None:
    """The shipped prompts/agents/summarize-day.md must be a valid spec."""
    spec = parse_spec(AGENT_SPECS_DIR / "summarize-day.md")
    assert spec.id == "summarize-day"
    assert spec.model == "claude-haiku-4-5"
    assert "Read" in spec.allowed_tools
    assert "Edit" in spec.allowed_tools
    assert spec.button is not None
    assert spec.button.shell_command_id == "agent-summarize-day"


def test_summarize_day_body_renders_with_today() -> None:
    """${today} placeholder gets substituted into the prompt body."""
    spec = parse_spec(AGENT_SPECS_DIR / "summarize-day.md")
    rendered = spec.render_body(today="2026-05-02", now="2026-05-02T10:00:00+02:00")
    assert "daily/2026-05-02.md" in rendered
    assert "${today}" not in rendered
    assert "${now}" not in rendered


def test_summarize_day_runs_against_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end smoke: spec resolution → mocked SDK → log persistence → last_run update."""
    import agent_task

    spec_src = (AGENT_SPECS_DIR / "summarize-day.md").read_text(encoding="utf-8")
    spec_copy = tmp_path / "summarize-day.md"
    spec_copy.write_text(spec_src, encoding="utf-8")
    spec = parse_spec(spec_copy)

    fake_logs_dir = tmp_path / "logs"

    async def fake_query(*, prompt: str, options):  # type: ignore[no-untyped-def]
        from claude_agent_sdk import ResultMessage
        msg = ResultMessage(
            subtype="success",
            duration_ms=10, duration_api_ms=10,
            is_error=False, num_turns=1, session_id="sess-test",
            total_cost_usd=0.0, usage={"input_tokens": 100, "output_tokens": 50},
            result="Pretended to write a Summary block. Done.",
        )
        yield msg

    monkeypatch.setattr(agent_task, "query", fake_query)
    monkeypatch.setattr(agent_task, "LOGS_DIR", fake_logs_dir)

    rc = asyncio.run(agent_task.run(spec, dry_run=False, extra_vars={}))
    assert rc == 0

    # Log file written
    logs = list(fake_logs_dir.glob("agent-summarize-day-*.log"))
    assert len(logs) == 1
    log_text = logs[0].read_text(encoding="utf-8")
    assert "Pretended to write a Summary block" in log_text
    assert "agent: summarize-day" in log_text
    assert "tokens: input=" in log_text  # value depends on AssistantMessage emission

    # Frontmatter `last_run` got written back
    spec2 = parse_spec(spec_copy)
    assert isinstance(spec2.last_run, str)
    assert spec2.last_run.startswith("20")
