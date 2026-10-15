"""M033-S04-T06 — characterisation of `facts.takes_producer.maybe_extract_takes` with a
fake SDK stream: the gates, the SDK options, the parse tolerances, the appended /
duplicate / dropped accounting and the SDK-failure path. Written before the split; the
take substrate itself is covered by test_takes.py."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from core.config import CONFIG
from facts import take, takes_producer

RESPONSE = {
    "takes": [
        {
            "holder": "Bob Example",
            "belief": "Hetzner will raise prices next year",
            "confidence": "high",
            "source": "raw/notes/hetzner.md",
        },
        {"holder": "Carol", "belief": "The admin fee is negotiable", "confidence": "medium"},
    ]
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    from core import paths

    takes_dir = tmp_path / "knowledge" / "takes"
    monkeypatch.setattr(take, "TAKES_DIR", takes_dir)
    monkeypatch.setattr(paths, "TAKES_DIR", takes_dir)
    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", takes_dir.parent)
    monkeypatch.setattr(takes_producer, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(CONFIG.features, "extract_takes", True)
    monkeypatch.setattr(CONFIG.limits, "extract_takes_source_globs", [])
    monkeypatch.setattr(CONFIG.limits, "extract_takes_max_per_source", 10)
    monkeypatch.setattr(CONFIG.personal, "implicit_operator_author", "Alex")
    src = tmp_path / "raw" / "notes" / "hetzner.md"
    src.parent.mkdir(parents=True)
    src.write_text(
        "Bob thinks Hetzner will raise prices. Carol says the admin fee is negotiable.",
        encoding="utf-8",
    )
    return tmp_path, src, takes_dir


def _install_stream(monkeypatch, *, result=None, assistant=(), error=None, seen=None):
    """Patch the SDK `query` with a stream of AssistantMessages + an optional
    ResultMessage; `error` raises on first iteration; `seen` records prompt + options."""

    async def _fake_query(*, prompt, options):
        if seen is not None:
            seen.update(prompt=prompt, options=options)
        if error is not None:
            raise error
        for text in assistant:
            yield AssistantMessage(content=[TextBlock(text=text)], model="m")
        if result is not None:
            yield ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
                usage={},
                result=result,
            )

    monkeypatch.setattr(takes_producer, "query", _fake_query)


def _run(src):
    asyncio.run(takes_producer.maybe_extract_takes(src))


def _boom(**kw):  # pragma: no cover - must never fire
    raise AssertionError("SDK called despite a gate")


def _takes_files(takes_dir):
    return sorted(p.name for p in takes_dir.glob("*.md")) if takes_dir.exists() else []


# ── the write path ───────────────────────────────────────────────────


def test_takes_are_appended_then_deduplicated(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, takes_dir = env
    seen: dict = {}
    _install_stream(monkeypatch, result=json.dumps(RESPONSE), seen=seen)

    _run(src)

    assert _takes_files(takes_dir) == ["bob-example.md", "carol.md"]
    bob = (takes_dir / "bob-example.md").read_text(encoding="utf-8")
    assert "Hetzner will raise prices next year" in bob and "raw/notes/hetzner.md" in bob
    carol = (takes_dir / "carol.md").read_text(encoding="utf-8")
    assert "The admin fee is negotiable" in carol and "raw/notes/hetzner.md" in carol
    assert (
        f"  Takes pass for raw/notes/hetzner.md (model={CONFIG.models.compile_model})"
        in caplog.text
    )
    assert "  Takes: 2 appended, 0 duplicate, 0 dropped (raw=2)" in caplog.text
    # The SDK saw the rendered prompt and a read-only, three-turn option set.
    assert "raw/notes/hetzner.md" in seen["prompt"] and "Alex" in seen["prompt"]
    opts = seen["options"]
    assert opts.allowed_tools == ["Read"] and opts.max_turns == 3
    assert opts.model == CONFIG.models.compile_model and opts.permission_mode == "default"
    assert opts.setting_sources == [] and opts.cwd == str(root)

    caplog.clear()
    _run(src)
    assert "  Takes: 0 appended, 2 duplicate, 0 dropped (raw=2)" in caplog.text


def test_drops_malformed_operator_authored_and_capped_takes(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    _root, src, takes_dir = env
    takes = [
        "not a dict",
        {"holder": "", "belief": "no holder", "confidence": "high"},
        {"holder": "Dan", "belief": "", "confidence": "high"},
        {"holder": "Eve", "belief": "bad confidence", "confidence": "certain"},
        {"holder": "alex", "belief": "the operator's own view", "confidence": "high"},
        {"holder": "Frank", "belief": "lands", "confidence": "low"},
    ]
    _install_stream(monkeypatch, result=json.dumps({"takes": takes}))

    _run(src)

    assert _takes_files(takes_dir) == ["frank.md"]
    assert "  Takes: 1 appended, 0 duplicate, 5 dropped (raw=6)" in caplog.text

    monkeypatch.setattr(CONFIG.limits, "extract_takes_max_per_source", 1)
    caplog.clear()
    _install_stream(monkeypatch, result=json.dumps(RESPONSE))
    _run(src)
    assert _takes_files(takes_dir) == ["bob-example.md", "frank.md"]
    assert "  Takes: 1 appended, 0 duplicate, 0 dropped (raw=2)" in caplog.text


# ── the model's answer ───────────────────────────────────────────────


def test_fenced_prose_wrapped_list_and_assistant_only_answers(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    _root, src, takes_dir = env
    body = json.dumps(RESPONSE)

    _install_stream(monkeypatch, result=f"```json\n{body}\n```")
    _run(src)
    assert _takes_files(takes_dir) == ["bob-example.md", "carol.md"]

    _install_stream(monkeypatch, result=f"Here are the takes: {body}")
    _run(src)
    assert "  Takes: 0 appended, 2 duplicate, 0 dropped (raw=2)" in caplog.text

    _install_stream(monkeypatch, result=json.dumps(RESPONSE["takes"]))
    _run(src)
    assert "0 appended, 2 duplicate" in caplog.text

    # No ResultMessage — the last assistant text block is the fallback.
    _install_stream(monkeypatch, assistant=["thinking…", body])
    caplog.clear()
    _run(src)
    assert "  Takes: 0 appended, 2 duplicate, 0 dropped (raw=2)" in caplog.text


def test_empty_non_json_invalid_and_unexpected_answers(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    _root, src, takes_dir = env

    _install_stream(monkeypatch, result="   ")
    _run(src)
    assert "  Takes: empty model response" in caplog.text

    _install_stream(monkeypatch, result="nope, nothing here")
    _run(src)
    assert "  Takes: model did not return JSON; first 200 chars='nope, nothing here'" in caplog.text

    _install_stream(monkeypatch, result="prose {bad json")
    _run(src)
    assert "  Takes: invalid JSON: prose {bad json" in caplog.text

    _install_stream(monkeypatch, result="42")
    _run(src)
    assert "  Takes: unexpected response type int" in caplog.text

    _install_stream(monkeypatch, result=json.dumps({"other": []}))
    _run(src)
    assert "  Takes: none extracted" in caplog.text

    assert _takes_files(takes_dir) == []


def test_sdk_failure_is_diagnosed_and_skips_the_source(env, monkeypatch) -> None:
    _root, src, takes_dir = env
    recorded: dict = {}

    def _fake_log_sdk_failure(log, **kw):
        recorded.update(kw)

    monkeypatch.setattr(takes_producer, "log_sdk_failure", _fake_log_sdk_failure)
    _install_stream(monkeypatch, error=RuntimeError("boom"))

    _run(src)

    assert _takes_files(takes_dir) == []
    assert recorded["label"] == "extract_takes"
    assert recorded["source"] == "raw/notes/hetzner.md"
    assert recorded["model"] == CONFIG.models.compile_model
    assert recorded["input_chars"] == len(src.read_text(encoding="utf-8"))
    assert str(recorded["exc"]) == "boom"


# ── the gates ────────────────────────────────────────────────────────


def test_gates_skip_before_the_sdk(env, monkeypatch) -> None:
    root, src, takes_dir = env
    monkeypatch.setattr(takes_producer, "query", _boom)

    monkeypatch.setattr(CONFIG.features, "extract_takes", False)
    _run(src)
    monkeypatch.setattr(CONFIG.features, "extract_takes", True)

    forbidden = root / "knowledge" / "concepts" / "x.md"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text("the operator's own article", encoding="utf-8")
    _run(forbidden)

    monkeypatch.setattr(CONFIG.limits, "extract_takes_source_globs", ["raw/transcripts/*"])
    _run(src)
    monkeypatch.setattr(CONFIG.limits, "extract_takes_source_globs", [])

    empty = root / "raw" / "notes" / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    _run(empty)

    _run(root / "raw" / "notes")  # a directory: the read fails, the pass returns

    assert _takes_files(takes_dir) == []
