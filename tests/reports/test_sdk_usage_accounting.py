"""LEDGER accounting for the reports-lib SDK call sites (M021 S01).

inference.py + analyst.py carried the documented-wrong token-summing
pattern (summing per-turn ``usage["input_tokens"]`` — the uncached delta
only), so every study/analyst run under-recorded input by orders of
magnitude under prompt-caching (see ``UsageTokens`` in sdk_helpers).
These tests pin the fixed behaviour: both sites route through
``run_sdk_query`` and the LEDGER receives the CACHE-INCLUSIVE totals
(``ResultMessage.usage`` preferred — DECISIONS 2026-06-02), while the
wedge scope-lock composition (deny-all-writes gate + streaming prompt +
disallowed tools + setting_sources) is preserved.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import scripts.core.usage as usage_mod
from scripts.reports._engine.lib import analyst as analyst_mod
from scripts.reports._engine.lib import inference as inf
from scripts.reports._engine.lib.inference import InferenceBatch
from scripts.reports._engine.lib.likert import LikertItem, LikertScale


def _assistant(usage: dict | None, text: str):
    from claude_agent_sdk import AssistantMessage, TextBlock
    return AssistantMessage(content=[TextBlock(text=text)], model="m", usage=usage)


def _result(usage: dict | None, cost: float = 0.3, result: str = ""):
    from claude_agent_sdk import ResultMessage
    return ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
        num_turns=1, session_id="t", total_cost_usd=cost, usage=usage,
        result=result,
    )


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Spy on the process-global LEDGER the reports lib records into.

    Patches the shared object's ``record`` method (not the module binding)
    so the capture works regardless of which import path the call site
    uses to reach the ledger."""
    calls: list[dict] = []

    def _record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(usage_mod.LEDGER, "record", _record)
    return calls


_TURN_USAGE = {
    "input_tokens": 10,
    "cache_creation_input_tokens": 1_000,
    "cache_read_input_tokens": 500,
    "output_tokens": 5,
}
_RESULT_USAGE = {
    "input_tokens": 12,
    "cache_creation_input_tokens": 2_000,
    "cache_read_input_tokens": 800,
    "output_tokens": 7,
}


class TestInferenceAccounting:
    def _batch(self) -> InferenceBatch:
        scale = LikertScale(lo=0, hi=3)
        return InferenceBatch(label="all", items=(LikertItem(id="1", scale=scale),))

    def test_ledger_gets_cache_inclusive_result_usage(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent_json = (
            '{"items": {"1": {"answer": 2, "confidence": 0.9, '
            '"evidence": [{"file": "daily/x.md", "quote": "q"}], '
            '"reasoning": "r"}}}'
        )

        async def fake_query(*, prompt, options):  # noqa: ARG001
            yield _assistant(_TURN_USAGE, agent_json)
            yield _result(_RESULT_USAGE, cost=0.31)

        monkeypatch.setattr(inf, "query", fake_query)

        result = asyncio.run(
            inf._infer_batch_once_async(
                "rendered prompt", self._batch(),
                vault_cwd=Path("/tmp"), prompt_version="pv",
            )
        )

        assert result.cost_usd == pytest.approx(0.31)
        assert result.items["1"].answer == 2
        assert len(recorded) == 1
        # ResultMessage.usage preferred, cache-inclusive: 12 + 2000 + 800.
        assert recorded[0]["input_tokens"] == 2_812
        assert recorded[0]["output_tokens"] == 7
        assert recorded[0]["model"] == inf.DEFAULT_INFERENCE_MODEL

    def test_schema_invalid_still_records_spend(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Malformed agent output is still real spend — the SDK call
        succeeded; only the parse failed. The ledger must see it."""

        async def fake_query(*, prompt, options):  # noqa: ARG001
            yield _assistant(_TURN_USAGE, "no json here")
            yield _result(_RESULT_USAGE)

        monkeypatch.setattr(inf, "query", fake_query)

        with pytest.raises(inf.InferenceError) as ei:
            asyncio.run(
                inf._infer_batch_once_async(
                    "rendered prompt", self._batch(),
                    vault_cwd=Path("/tmp"), prompt_version="pv",
                )
            )
        assert ei.value.failure is not None
        assert ei.value.failure.kind == inf.SCHEMA_INVALID_KIND
        assert len(recorded) == 1
        assert recorded[0]["input_tokens"] == 2_812

    def test_sdk_failure_raises_inference_error_with_failure_kind(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom_query(*, prompt, options):  # noqa: ARG001
            raise RuntimeError("Command failed with exit code 1")
            yield  # pragma: no cover

        monkeypatch.setattr(inf, "query", boom_query)

        with pytest.raises(inf.InferenceError) as ei:
            asyncio.run(
                inf._infer_batch_once_async(
                    "rendered prompt", self._batch(),
                    vault_cwd=Path("/tmp"), prompt_version="pv",
                )
            )
        # Fast fail + empty stderr → cli_crash, which the retry ladder retries.
        assert ei.value.failure is not None
        assert ei.value.failure.kind == "cli_crash"

    def test_wedge_scope_lock_preserved(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The M019 wedge composition survives the harness migration:
        deny-all-writes gate + streaming prompt + disallowed tools +
        setting_sources=[project] + permission_mode=default."""
        captured: dict = {}
        agent_json = (
            '{"items": {"1": {"answer": null, "confidence": 0.0, '
            '"evidence": [], "reasoning": "none"}}}'
        )

        async def fake_query(*, prompt, options):
            captured["prompt"] = prompt
            captured["options"] = options
            yield _assistant(None, agent_json)
            yield _result(_RESULT_USAGE)

        monkeypatch.setattr(inf, "query", fake_query)
        asyncio.run(
            inf._infer_batch_once_async(
                "rendered prompt", self._batch(),
                vault_cwd=Path("/tmp"), prompt_version="pv",
            )
        )

        options = captured["options"]
        assert options.allowed_tools == list(inf.WEDGE_ALLOWED_TOOLS)
        assert options.disallowed_tools == list(inf.WEDGE_DISALLOWED_TOOLS)
        assert options.permission_mode == "default"
        assert options.setting_sources == ["project"]
        assert options.can_use_tool is not None
        # Deny-all gate: no write root is permitted.
        async def _deny():
            return await options.can_use_tool("Write", {"file_path": "/tmp/x"}, None)
        assert asyncio.run(_deny()).behavior == "deny"
        # Streaming prompt envelope (can_use_tool contract).
        assert not isinstance(captured["prompt"], str)


class TestAnalystAccounting:
    def test_ledger_gets_cache_inclusive_result_usage(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        persona = tmp_path / "analyst_per_study.md"
        persona.write_text("You are the analyst.\n", encoding="utf-8")

        async def fake_query(*, prompt, options):  # noqa: ARG001
            yield _assistant(_TURN_USAGE, "# Analysis body\n")
            yield _result(_RESULT_USAGE, cost=0.12)

        monkeypatch.setattr(analyst_mod, "query", fake_query)

        result = asyncio.run(
            analyst_mod._run_analyst_async(
                system_prompt_path=persona,
                user_prompt="study data",
                vault_cwd=tmp_path,
                pass_label="per-study",
                model="claude-haiku-4-5",
                max_turns=8,
            )
        )

        assert result.markdown_body == "# Analysis body"
        assert result.cost_usd == pytest.approx(0.12)
        assert len(recorded) == 1
        assert recorded[0]["input_tokens"] == 2_812
        assert recorded[0]["output_tokens"] == 7

    def test_empty_body_raises_but_records_spend(
        self, recorded: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        persona = tmp_path / "analyst_per_study.md"
        persona.write_text("persona\n", encoding="utf-8")

        async def fake_query(*, prompt, options):  # noqa: ARG001
            yield _result(_RESULT_USAGE)

        monkeypatch.setattr(analyst_mod, "query", fake_query)

        with pytest.raises(analyst_mod.AnalystError):
            asyncio.run(
                analyst_mod._run_analyst_async(
                    system_prompt_path=persona,
                    user_prompt="study data",
                    vault_cwd=tmp_path,
                    pass_label="per-study",
                    model="claude-haiku-4-5",
                    max_turns=8,
                )
            )
        assert len(recorded) == 1
        assert recorded[0]["input_tokens"] == 2_812
