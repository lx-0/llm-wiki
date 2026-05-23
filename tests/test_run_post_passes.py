"""Tests for compile_stages.post_passes.run_post_passes (M018-S04-T03).

Mirrors test_producer_registry's ``_isolate_registry`` autouse fixture so
each case starts with an empty Registry and the real producers (the live
suggestions/curiosity/takes) don't bleed in.

The post-pass loop's contract is thin: iterate Registry, call
``evaluate_and_run`` for each, collect results. It does NOT mutate state
(per-producer usage is recorded centrally via the token ledger). Tests
assert ordering, failure-isolation, and gate-skip, mocking the orchestrator
where it lets us test the loop's behavior without real producer bodies.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Each test gets a clean Registry — no leakage between tests."""
    from producers import base as producers_base

    saved = dict(producers_base._PRODUCERS)
    producers_base._PRODUCERS.clear()
    yield
    producers_base._PRODUCERS.clear()
    producers_base._PRODUCERS.update(saved)


def _make_fake_producer(name: str, raises: bool = False,
                       enabled_key: str | None = None):
    """Build a Producer class that records each run() call site-effectfully.

    The class carries a ``calls`` class attribute that test bodies can
    assert against. ``raises=True`` makes run() raise — the orchestrator's
    wrapper catches and returns ``ProducerResult(status="failed")``.
    """
    from producers.base import ProducerResult, ProducerSpec, register

    class _P:
        SPEC = ProducerSpec(
            name=name,
            enabled_config_key=enabled_key,
            source_glob_config_key=None,
        )
        calls: list[Path] = []

        async def run(self, source: Path) -> ProducerResult:
            type(self).calls.append(source)
            if raises:
                raise RuntimeError(f"{name} blew up")
            return ProducerResult(producer=name, status="ok")

    _P.__qualname__ = f"_Fake_{name}"
    _P.calls = []
    register(_P)
    return _P


def _stub_orchestrate_failed_on_raise(monkeypatch: pytest.MonkeyPatch):
    """Wrap evaluate_and_run as run_post_passes sees it: catch raises
    from Producer.run() and surface as ProducerResult(failed).

    The real orchestrator only catches at the wrapper layer (S02 Producer
    wrappers); our raw fake producers raise straight from run(). We
    monkeypatch the symbol the post_passes module imports.
    """
    import compile_stages.post_passes as pp_mod
    from producers.base import ProducerResult
    from producers.orchestrate import evaluate_and_run as real_eval

    async def safe_eval(producer, source):
        try:
            return await real_eval(producer, source)
        except Exception as exc:  # noqa: BLE001
            return ProducerResult(
                producer=producer.SPEC.name,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )

    monkeypatch.setattr(pp_mod, "evaluate_and_run", safe_eval)


# ── (1) All gates pass — 3 producers run, costs accumulate ────────────


def test_run_post_passes_all_three_run(monkeypatch: pytest.MonkeyPatch):
    from compile_stages.post_passes import run_post_passes
    from compile_stages.types import CompileResult

    _stub_orchestrate_failed_on_raise(monkeypatch)

    p1 = _make_fake_producer("p1")
    p2 = _make_fake_producer("p2")
    p3 = _make_fake_producer("p3")

    state: dict = {}
    source = Path("/tmp/raw/notes/x.md")
    cr = CompileResult(status="ok", article="body")

    results = asyncio.run(run_post_passes(source, cr, state))

    assert len(results) == 3
    assert [r.producer for r in results] == ["p1", "p2", "p3"]
    assert all(r.status == "ok" for r in results), results
    assert p1.calls == [source]
    assert p2.calls == [source]
    assert p3.calls == [source]
    assert state == {}  # run_post_passes no longer mutates state (usage → ledger)


# ── (2) Raising producer surfaces as failed; subsequent producers run ──


def test_run_post_passes_raise_does_not_block(monkeypatch: pytest.MonkeyPatch):
    from compile_stages.post_passes import run_post_passes
    from compile_stages.types import CompileResult

    _stub_orchestrate_failed_on_raise(monkeypatch)

    p1 = _make_fake_producer("p1")
    p2 = _make_fake_producer("p2", raises=True)
    p3 = _make_fake_producer("p3")

    state: dict = {}
    source = Path("/tmp/raw/notes/y.md")
    cr = CompileResult(status="ok", article="body")

    results = asyncio.run(run_post_passes(source, cr, state))

    assert [r.status for r in results] == ["ok", "failed", "ok"]
    assert [r.producer for r in results] == ["p1", "p2", "p3"]
    # Third producer was still called despite the second raising.
    assert p3.calls == [source]


# ── (3) Gate-skipped producer returns skipped without invoking run() ──


def test_run_post_passes_gate_skip_does_not_call_run(monkeypatch: pytest.MonkeyPatch):
    from compile_stages.post_passes import run_post_passes
    from compile_stages.types import CompileResult

    _stub_orchestrate_failed_on_raise(monkeypatch)

    p1 = _make_fake_producer("p1")
    # CONFIG.features.nope does not exist → orchestrator gates this out as skipped.
    p2 = _make_fake_producer("p2", enabled_key="features.nope")
    p3 = _make_fake_producer("p3")

    state: dict = {}
    source = Path("/tmp/raw/notes/z.md")
    cr = CompileResult(status="ok", article="body")

    results = asyncio.run(run_post_passes(source, cr, state))

    assert [r.status for r in results] == ["ok", "skipped", "ok"]
    assert p1.calls == [source]
    assert p2.calls == [], "gate-skipped producer's run() must NOT be called"
    assert p3.calls == [source]


# ── (4) Empty Registry → empty result, no state mutation ──────────────


def test_run_post_passes_empty_registry(monkeypatch: pytest.MonkeyPatch):
    from compile_stages.post_passes import run_post_passes
    from compile_stages.types import CompileResult

    _stub_orchestrate_failed_on_raise(monkeypatch)

    state: dict = {"existing_key": "untouched"}
    source = Path("/tmp/raw/notes/empty.md")
    cr = CompileResult(status="ok", article="body")

    results = asyncio.run(run_post_passes(source, cr, state))

    assert results == []
    assert "producer_cost_total" not in state
    assert state == {"existing_key": "untouched"}
