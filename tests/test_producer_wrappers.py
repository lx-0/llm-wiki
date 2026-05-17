"""Tests for the three concrete Producer wrappers (S02 of Producer-seam arc).

Each wrapper is a thin class around the legacy free function in
`suggestions/producer.py`, `curiosity/producer.py`, `facts/takes_producer.py`.
Wrappers must:
- declare correct SPEC (name + gate config keys)
- catch exceptions from the legacy function → return `failed` ProducerResult
- return `ok` ProducerResult on clean completion

Gate-evaluation is NOT tested here — that's the orchestrator's job (S03).
For S02, gates stay internal in the legacy fn; wrapper just delegates.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ── Suggestions wrapper ──────────────────────────────────────────────


def test_suggestions_spec_shape():
    from producers.suggestions import SuggestionsProducer

    spec = SuggestionsProducer.SPEC
    assert spec.name == "suggestions"
    # Top-level enable flag: none today (suggestions always runs internally;
    # filter via source-glob). Declared so future opt-out is one CONFIG add.
    assert spec.enabled_config_key is None
    # Forward-looking: the source-glob key lands in S03's migration; the
    # orchestrator (also S03) will consult it. For S02 the legacy fn still
    # does its own hardcoded _is_email_source check.
    assert spec.source_glob_config_key == "features.suggestions_source_globs"


def test_suggestions_run_ok(monkeypatch, tmp_path):
    """Successful delegation → ok result with producer=suggestions."""
    import producers.suggestions as mod
    from producers.base import ProducerResult

    called = {}

    async def _fake(source: Path, dry_run: bool = False) -> None:
        called["source"] = source

    monkeypatch.setattr(mod, "maybe_generate_suggestions", _fake)

    src = tmp_path / "source.md"
    src.write_text("body")

    p = mod.SuggestionsProducer()
    result = asyncio.run(p.run(src))

    assert isinstance(result, ProducerResult)
    assert result.producer == "suggestions"
    assert result.status == "ok"
    assert called["source"] == src


def test_suggestions_run_catches_exception(monkeypatch, tmp_path):
    """Legacy fn raising → wrapper returns failed result, does not propagate."""
    import producers.suggestions as mod

    async def _boom(source: Path, dry_run: bool = False) -> None:
        raise RuntimeError("ollama timeout")

    monkeypatch.setattr(mod, "maybe_generate_suggestions", _boom)

    src = tmp_path / "source.md"
    src.write_text("body")

    p = mod.SuggestionsProducer()
    result = asyncio.run(p.run(src))

    assert result.status == "failed"
    assert result.reason is not None
    assert "ollama timeout" in result.reason


# ── Curiosity wrapper ────────────────────────────────────────────────


def test_curiosity_spec_shape():
    from producers.curiosity import CuriosityProducer

    spec = CuriosityProducer.SPEC
    assert spec.name == "curiosity"
    assert spec.enabled_config_key == "features.curiosity_loop"
    assert spec.source_glob_config_key is None


def test_curiosity_run_ok(monkeypatch, tmp_path):
    import producers.curiosity as mod
    from producers.base import ProducerResult

    async def _fake(source: Path) -> None:
        return None

    monkeypatch.setattr(mod, "maybe_generate_curiosity_requests", _fake)

    src = tmp_path / "x.md"
    src.write_text("body")

    p = mod.CuriosityProducer()
    result = asyncio.run(p.run(src))

    assert isinstance(result, ProducerResult)
    assert result.producer == "curiosity"
    assert result.status == "ok"


def test_curiosity_run_catches_exception(monkeypatch, tmp_path):
    import producers.curiosity as mod

    async def _boom(source: Path) -> None:
        raise ValueError("schema mismatch")

    monkeypatch.setattr(mod, "maybe_generate_curiosity_requests", _boom)

    src = tmp_path / "x.md"
    src.write_text("body")

    p = mod.CuriosityProducer()
    result = asyncio.run(p.run(src))

    assert result.status == "failed"
    assert "schema mismatch" in (result.reason or "")


# ── Takes wrapper ────────────────────────────────────────────────────


def test_takes_spec_shape():
    from producers.takes import TakesProducer

    spec = TakesProducer.SPEC
    assert spec.name == "takes"
    assert spec.enabled_config_key == "features.extract_takes"
    assert spec.source_glob_config_key == "limits.extract_takes_source_globs"


def test_takes_run_ok(monkeypatch, tmp_path):
    import producers.takes as mod
    from producers.base import ProducerResult

    async def _fake(source: Path) -> None:
        return None

    monkeypatch.setattr(mod, "maybe_extract_takes", _fake)

    src = tmp_path / "x.md"
    src.write_text("body")

    p = mod.TakesProducer()
    result = asyncio.run(p.run(src))

    assert isinstance(result, ProducerResult)
    assert result.producer == "takes"
    assert result.status == "ok"


def test_takes_run_catches_exception(monkeypatch, tmp_path):
    import producers.takes as mod

    async def _boom(source: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mod, "maybe_extract_takes", _boom)

    src = tmp_path / "x.md"
    src.write_text("body")

    p = mod.TakesProducer()
    result = asyncio.run(p.run(src))

    assert result.status == "failed"
    assert "disk full" in (result.reason or "")


# ── Registry: package-import triggers registration ───────────────────


def test_package_import_registers_all_three():
    """`import producers` must register the three concrete producers in
    the documented order: suggestions → curiosity → takes."""
    # Fresh import path: clear any modules we touched + reload `producers`
    # via importlib so __init__ side-effects fire under a clean Registry.
    import importlib
    import sys

    import producers.base as base_mod

    for mod_name in [
        "producers.suggestions",
        "producers.curiosity",
        "producers.takes",
        "producers",
    ]:
        sys.modules.pop(mod_name, None)
    saved = dict(base_mod._PRODUCERS)
    base_mod._PRODUCERS.clear()

    try:
        importlib.import_module("producers")
        from producers.base import all_producers

        names = [p.SPEC.name for p in all_producers()]
        assert names == ["suggestions", "curiosity", "takes"]
    finally:
        base_mod._PRODUCERS.clear()
        base_mod._PRODUCERS.update(saved)
