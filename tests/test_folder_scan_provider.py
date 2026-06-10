"""Tests for the folder-scan provider seam (curiosity/backends/folder_providers.py).

M027-S04-T01 (closes Q9): the agentic read+answer sits behind a
config-selected provider — Claude SDK today, a local LLM/agent later with
the same request/answer contract. NO silent fallback: an unknown provider
name is a loud ConfigError. The Claude provider reads exactly ONE named
file via `allowed_tools=["Read"]` + a PreToolUse path-scope hook
(file-as-root) — the load-bearing wiring is asserted on the captured
ClaudeAgentOptions. SDK fully mocked (test_compile_source pattern).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.config import CONFIG, ConfigError


def _result_message(result: str = "distilled answer", cost: float = 0.01):
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="t",
        total_cost_usd=cost,
        usage={"input_tokens": 1000, "output_tokens": 200},
        result=result,
    )


@pytest.fixture
def trove_file(tmp_path: Path):
    f = tmp_path / "11 Steuern" / "Steuerbescheid-2024.pdf"
    f.parent.mkdir(parents=True)
    f.write_text("secret document body", encoding="utf-8")
    return f


def test_get_provider_returns_claude_sdk_on_default():
    from curiosity.backends import folder_providers as fp

    provider = fp.get_provider()
    assert isinstance(provider, fp.ClaudeSdkProvider)


def test_unknown_provider_name_is_loud_config_error(monkeypatch):
    from curiosity.backends import folder_providers as fp

    monkeypatch.setattr(CONFIG.models, "folder_scan_provider", "ollama-magic")
    with pytest.raises(ConfigError, match="ollama-magic"):
        fp.get_provider()


def test_claude_provider_happy_path_scopes_read_to_the_file(
    trove_file, monkeypatch
):
    from curiosity.backends import folder_providers as fp

    captured = {}

    async def fake_query(*, prompt, options):  # noqa: ARG001
        captured["options"] = options
        yield _result_message(result="## Answer\n\nFinal amount: 1234 EUR")

    monkeypatch.setattr(fp, "query", fake_query)
    monkeypatch.setattr(fp, "render", lambda name, **kw: f"PROMPT[{name}]")

    answer = asyncio.run(
        fp.get_provider().answer(
            topic="Steuerbescheid 2024 final amount",
            rationale="filename names it",
            file_abs=trove_file,
            file_rel="11 Steuern/Steuerbescheid-2024.pdf",
        )
    )
    assert answer.error is None
    assert "1234 EUR" in answer.answer_md
    assert answer.as_of_mtime == trove_file.stat().st_mtime
    assert answer.file_path == "11 Steuern/Steuerbescheid-2024.pdf"

    opts = captured["options"]
    assert opts.allowed_tools == ["Read"]  # read-only, nothing else exposed
    assert opts.hooks and "PreToolUse" in opts.hooks  # path-scope wired
    assert str(trove_file.parent) == opts.cwd


def test_missing_file_propagates_file_not_found(tmp_path, monkeypatch):
    from curiosity.backends import folder_providers as fp

    async def fake_query(*, prompt, options):  # pragma: no cover
        raise AssertionError("SDK must not be called for a missing file")
        yield  # noqa: unreachable — makes this an async generator

    monkeypatch.setattr(fp, "query", fake_query)
    monkeypatch.setattr(fp, "render", lambda name, **kw: "PROMPT")
    with pytest.raises(FileNotFoundError):
        asyncio.run(
            fp.get_provider().answer(
                topic="t",
                rationale="r",
                file_abs=tmp_path / "gone.pdf",
                file_rel="gone.pdf",
            )
        )


def test_empty_sdk_result_is_error_not_exception(trove_file, monkeypatch):
    from curiosity.backends import folder_providers as fp

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield _result_message(result="")

    monkeypatch.setattr(fp, "query", fake_query)
    monkeypatch.setattr(fp, "render", lambda name, **kw: "PROMPT")

    answer = asyncio.run(
        fp.get_provider().answer(
            topic="t",
            rationale="r",
            file_abs=trove_file,
            file_rel="11 Steuern/Steuerbescheid-2024.pdf",
        )
    )
    assert answer.error == "empty_result"
    assert answer.answer_md == ""


def test_real_prompt_templates_render_with_provider_kwargs():
    """The actual prompts/folder_scan_answer{,_system}.md must render with
    exactly the kwargs the provider passes."""
    from core.prompts import render as real_render

    system = real_render("folder_scan_answer_system")
    assert "${" not in system
    user = real_render(
        "folder_scan_answer",
        topic="Steuerbescheid 2024 final amount",
        rationale="filename names it",
        file_rel="11 Steuern/Steuerbescheid-2024.pdf",
        file_abs="/troves/docs/11 Steuern/Steuerbescheid-2024.pdf",
    )
    assert "Steuerbescheid-2024.pdf" in user
    assert "NOT ANSWERED IN THIS FILE" in user  # sentinel contract (T03 uses it)
    assert "${" not in user
