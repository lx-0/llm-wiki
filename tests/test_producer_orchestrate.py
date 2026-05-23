"""Tests for producers.orchestrate.evaluate_and_run.

Orchestrator evaluates Spec gates (enabled_config_key + source_glob_config_key)
against CONFIG/source, short-circuits to `skipped` if a gate fails, otherwise
delegates to producer.run(). The producer's wrapper already returns a clean
ProducerResult (S02), so the orchestrator does not add a second try/except.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from producers.base import Producer, ProducerResult, ProducerSpec


def _stub_producer(
    name: str,
    enabled_key: str | None = None,
    glob_key: str | None = None,
    on_run: ProducerResult | Exception | None = None,
):
    """Build a stub producer that returns ``on_run`` (or 'ok' if None) when run."""

    class _Stub:
        SPEC = ProducerSpec(
            name=name, enabled_config_key=enabled_key, source_glob_config_key=glob_key
        )
        run_called = False

        async def run(self, source: Path) -> ProducerResult:
            type(self).run_called = True
            if isinstance(on_run, Exception):
                raise on_run
            return on_run or ProducerResult(producer=name, status="ok")

    _Stub.__name__ = f"Stub_{name}"
    _Stub.__qualname__ = _Stub.__name__
    return _Stub


def _mock_config(**features):
    """Build a fake CONFIG with features.* + limits.* attribute-chain access."""
    return SimpleNamespace(
        features=SimpleNamespace(**features.get("features", {})),
        limits=SimpleNamespace(**features.get("limits", {})),
    )


# ── enabled_config_key ───────────────────────────────────────────────


def test_enabled_key_none_proceeds_to_run(monkeypatch, tmp_path):
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "CONFIG", _mock_config())
    P = _stub_producer("x", enabled_key=None)
    src = tmp_path / "s.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "ok"
    assert P.run_called


def test_enabled_key_truthy_proceeds_to_run(monkeypatch, tmp_path):
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "CONFIG", _mock_config(features={"flag_x": True}))
    P = _stub_producer("x", enabled_key="features.flag_x")
    src = tmp_path / "s.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "ok"
    assert P.run_called


def test_enabled_key_falsy_skips(monkeypatch, tmp_path):
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "CONFIG", _mock_config(features={"flag_x": False}))
    P = _stub_producer("x", enabled_key="features.flag_x")
    src = tmp_path / "s.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "skipped"
    assert result.reason is not None
    assert "features.flag_x" in result.reason
    assert not P.run_called


def test_enabled_key_missing_attr_skips(monkeypatch, tmp_path):
    """Missing attribute on CONFIG path → treat as disabled (graceful)."""
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "CONFIG", _mock_config())
    P = _stub_producer("x", enabled_key="features.nope")
    src = tmp_path / "s.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "skipped"
    assert not P.run_called


# ── source_glob_config_key ───────────────────────────────────────────


def test_glob_key_none_proceeds_for_any_source(monkeypatch, tmp_path):
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "CONFIG", _mock_config())
    P = _stub_producer("x", glob_key=None)
    src = tmp_path / "anything.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "ok"
    assert P.run_called


def test_glob_key_matches_proceeds(monkeypatch, tmp_path, mocker_root):
    """Source matches one of the globs → run."""
    import producers.orchestrate as mod

    # source globs are matched against the source path relative to ROOT_DIR.
    # Mock ROOT_DIR so the test fixture path resolves cleanly.
    monkeypatch.setattr(mod, "ROOT_DIR", mocker_root)
    monkeypatch.setattr(
        mod,
        "CONFIG",
        _mock_config(features={"email_globs": ["raw/email/*.md"]}),
    )
    P = _stub_producer("x", glob_key="features.email_globs")

    src_dir = mocker_root / "raw" / "email"
    src_dir.mkdir(parents=True)
    src = src_dir / "msg.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "ok"
    assert P.run_called


def test_glob_key_no_match_skips(monkeypatch, tmp_path, mocker_root):
    """Source doesn't match any glob → skipped."""
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "ROOT_DIR", mocker_root)
    monkeypatch.setattr(
        mod,
        "CONFIG",
        _mock_config(features={"email_globs": ["raw/email/*.md"]}),
    )
    P = _stub_producer("x", glob_key="features.email_globs")

    src_dir = mocker_root / "raw" / "notes"
    src_dir.mkdir(parents=True)
    src = src_dir / "n.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "skipped"
    assert "glob" in (result.reason or "").lower()
    assert not P.run_called


def test_glob_key_empty_list_skips_everything(monkeypatch, tmp_path, mocker_root):
    """Empty allowlist = nothing applies (consistent with takes_producer)."""
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "ROOT_DIR", mocker_root)
    monkeypatch.setattr(mod, "CONFIG", _mock_config(features={"globs": []}))
    P = _stub_producer("x", glob_key="features.globs")

    src = mocker_root / "anywhere.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "skipped"
    assert not P.run_called


# ── Both gates pass → producer's result is returned verbatim ────────


def test_both_gates_pass_returns_producer_result(monkeypatch, tmp_path, mocker_root):
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "ROOT_DIR", mocker_root)
    monkeypatch.setattr(
        mod,
        "CONFIG",
        _mock_config(
            features={"on": True, "globs": ["*.md"]},
        ),
    )

    expected = ProducerResult(producer="x", status="ok")
    P = _stub_producer("x", enabled_key="features.on", glob_key="features.globs", on_run=expected)

    src = mocker_root / "any.md"
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result is expected


def test_failed_result_from_wrapper_passes_through(monkeypatch, tmp_path, mocker_root):
    """Producer wrapper returns a failed result → orchestrator does NOT
    re-wrap it. Single failure path."""
    import producers.orchestrate as mod

    monkeypatch.setattr(mod, "ROOT_DIR", mocker_root)
    monkeypatch.setattr(mod, "CONFIG", _mock_config())

    failed = ProducerResult(producer="x", status="failed", reason="legacy fn raised")
    P = _stub_producer("x", on_run=failed)

    src = mocker_root / "any.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("")

    result = asyncio.run(mod.evaluate_and_run(P(), src))
    assert result.status == "failed"
    assert result.reason == "legacy fn raised"


# ── Fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def mocker_root(tmp_path):
    """A pretend ROOT_DIR for glob-matching tests."""
    return tmp_path
