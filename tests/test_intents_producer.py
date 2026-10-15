"""M033-S04-T06 — characterisation of `producers.intents.IntentsProducer.run` with a fake
SDK stream and a recording `dispatch`: the seen-guard, the gates, the SDK options, the
parse tolerances, the confidence floor and every `ProducerResult` the loop returns.
Written before the split; the handlers + helpers are covered by test_intents.py."""

from __future__ import annotations

import asyncio
import json
import types

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from core.config import CONFIG
from producers import intents as intents_mod


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(intents_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(intents_mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(intents_mod, "_SEEN_STATE", tmp_path / "state" / "intents-seen.json")
    monkeypatch.setattr(CONFIG.limits, "intent_min_confidence", "high")
    src = tmp_path / "raw" / "voice" / "2026-10-15-note.md"
    src.parent.mkdir(parents=True)
    src.write_text("Remind me to send Bob the Hetzner invoice tomorrow.", encoding="utf-8")
    return tmp_path, src


def _install_stream(monkeypatch, *, result=None, assistant=(), error=None, seen=None):
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

    monkeypatch.setattr(intents_mod, "query", _fake_query)


def _install_dispatch(monkeypatch, *, output=None, error=None):
    calls: list = []

    def _fake_dispatch(intent):
        calls.append(intent)
        if error is not None:
            raise error
        return types.SimpleNamespace(status="created", output=output)

    monkeypatch.setattr(intents_mod, "dispatch", _fake_dispatch)
    return calls


def _run(src):
    return asyncio.run(intents_mod.IntentsProducer().run(src))


def _seen(root):
    p = root / "state" / "intents-seen.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _classification(kind="task", confidence="high", summary="Send Bob the Hetzner invoice"):
    return json.dumps({"kind": kind, "confidence": confidence, "summary": summary})


# ── dispatch outcomes ────────────────────────────────────────────────


def test_confident_task_is_dispatched_and_marked_seen(env, monkeypatch) -> None:
    root, src = env
    seen: dict = {}
    _install_stream(monkeypatch, result=_classification(), seen=seen)
    out = root / "workspace" / "inbox" / "task.md"
    calls = _install_dispatch(monkeypatch, output=out)

    res = _run(src)

    assert (res.producer, res.status, res.reason) == ("intents", "ok", "kind=task → created")
    assert res.outputs == (out,)
    [intent] = calls
    assert (intent.kind, intent.summary, intent.source, intent.confidence) == (
        "task",
        "Send Bob the Hetzner invoice",
        "raw/voice/2026-10-15-note.md",
        "high",
    )
    assert _seen(root) == ["raw/voice/2026-10-15-note.md"]
    assert "raw/voice/2026-10-15-note.md" in seen["prompt"]
    opts = seen["options"]
    assert opts.allowed_tools == ["Read"] and opts.max_turns == 3
    assert opts.permission_mode == "default" and opts.setting_sources == []
    assert opts.cwd == str(root)


def test_task_below_the_confidence_floor_is_not_dispatched(env, monkeypatch) -> None:
    root, src = env
    _install_stream(monkeypatch, result=_classification(confidence="medium"))
    calls = _install_dispatch(monkeypatch)

    res = _run(src)

    assert (res.status, res.reason) == ("ok", "task below confidence floor (conf=medium)")
    assert calls == [] and res.outputs == ()
    assert _seen(root) == ["raw/voice/2026-10-15-note.md"]


def test_idea_is_dispatched_regardless_of_confidence(env, monkeypatch) -> None:
    _root, src = env
    _install_stream(monkeypatch, result=_classification(kind="idea", confidence="low"))
    calls = _install_dispatch(monkeypatch, output=None)

    res = _run(src)

    assert (res.status, res.reason, res.outputs) == ("ok", "kind=idea → created", ())
    assert [c.kind for c in calls] == ["idea"]


def test_none_is_noise(env, monkeypatch) -> None:
    root, src = env
    _install_stream(monkeypatch, result=_classification(kind="none", confidence="low", summary=""))
    calls = _install_dispatch(monkeypatch)

    res = _run(src)

    assert (res.status, res.reason) == ("ok", "kind=none (noise)")
    assert calls == [] and _seen(root) == ["raw/voice/2026-10-15-note.md"]


def test_dispatch_exception_is_a_failed_result(env, monkeypatch) -> None:
    _root, src = env
    _install_stream(monkeypatch, result=_classification())
    _install_dispatch(monkeypatch, error=RuntimeError("inbox gone"))

    res = _run(src)

    assert (res.status, res.reason) == ("failed", "dispatch RuntimeError: inbox gone")


# ── the guards ───────────────────────────────────────────────────────


def test_already_seen_source_is_skipped_before_the_sdk(env, monkeypatch) -> None:
    root, src = env
    (root / "state").mkdir()
    (root / "state" / "intents-seen.json").write_text(
        json.dumps(["raw/voice/2026-10-15-note.md"]), encoding="utf-8"
    )

    def _boom(**kw):  # pragma: no cover
        raise AssertionError("SDK called for a seen source")

    monkeypatch.setattr(intents_mod, "query", _boom)

    res = _run(src)

    assert (res.status, res.reason) == (
        "skipped",
        "already classified: raw/voice/2026-10-15-note.md",
    )


def test_empty_source_is_skipped_and_marked_seen(env, monkeypatch) -> None:
    root, src = env
    src.write_text("  \n", encoding="utf-8")

    res = _run(src)

    assert (res.status, res.reason) == ("skipped", "empty source")
    assert _seen(root) == ["raw/voice/2026-10-15-note.md"]


def test_unreadable_source_fails(env, monkeypatch) -> None:
    root, _src = env

    res = _run(root / "raw" / "voice")  # a directory

    assert res.status == "failed" and res.reason.startswith("read failed: ")


def test_source_outside_the_vault_keys_by_name(env, monkeypatch, tmp_path_factory) -> None:
    root, _src = env
    outside = tmp_path_factory.mktemp("elsewhere") / "stray.md"
    outside.write_text("Idea: a stray note", encoding="utf-8")
    _install_stream(monkeypatch, result=_classification(kind="note", confidence="low"))
    calls = _install_dispatch(monkeypatch)

    res = _run(outside)

    assert res.status == "ok" and calls[0].source == "stray.md"
    assert _seen(root) == ["stray.md"]


# ── the model's answer ───────────────────────────────────────────────


def test_sdk_failure_is_diagnosed(env, monkeypatch) -> None:
    root, src = env
    recorded: dict = {}
    monkeypatch.setattr(intents_mod, "log_sdk_failure", lambda log, **kw: recorded.update(kw))
    _install_stream(monkeypatch, error=RuntimeError("boom"))

    res = _run(src)

    assert (res.status, res.reason) == ("failed", "RuntimeError: boom")
    assert recorded["label"] == "intent_classify"
    assert recorded["source"] == "raw/voice/2026-10-15-note.md"
    assert recorded["input_chars"] == len(src.read_text(encoding="utf-8"))
    assert _seen(root) is None


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        ("   ", "empty model response"),
        ("nope", "non-JSON response: 'nope'"),
        ("prose {bad", "invalid JSON: 'prose {bad'"),
        ("[1, 2]", "unexpected response type list"),
    ],
)
def test_unusable_answers_fail_without_marking_seen(env, monkeypatch, result, reason) -> None:
    root, src = env
    _install_stream(monkeypatch, result=result)

    res = _run(src)

    assert (res.status, res.reason) == ("failed", reason)
    assert _seen(root) is None


def test_fenced_prose_wrapped_and_assistant_only_answers_parse(env, monkeypatch) -> None:
    _root, src = env
    body = _classification(kind="note", confidence="low")
    calls = _install_dispatch(monkeypatch)

    _install_stream(monkeypatch, result=f"```json\n{body}\n```")
    assert _run(src).reason == "kind=note → created"

    (_root / "state" / "intents-seen.json").unlink()
    _install_stream(monkeypatch, result=f"Classified: {body}")
    assert _run(src).reason == "kind=note → created"

    (_root / "state" / "intents-seen.json").unlink()
    _install_stream(monkeypatch, assistant=["working…", body])
    assert _run(src).reason == "kind=note → created"

    assert len(calls) == 3
