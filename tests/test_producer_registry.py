"""Tests for scripts/producers/base.py — Spec / Result / Protocol / Registry.

Mirrors the Collector pattern at scripts/collectors/base.py + design doc
.ytstack/backlog/producer-seam.md (Milestone-A, Slice S01).
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── Spec / Result shape ──────────────────────────────────────────────


def test_producer_spec_required_fields():
    from producers.base import ProducerSpec

    spec = ProducerSpec(
        name="example",
        enabled_config_key=None,
        source_glob_config_key=None,
    )
    assert spec.name == "example"
    assert spec.enabled_config_key is None
    assert spec.source_glob_config_key is None


def test_producer_spec_is_frozen():
    from producers.base import ProducerSpec

    spec = ProducerSpec(name="x", enabled_config_key=None, source_glob_config_key=None)
    with pytest.raises((AttributeError, Exception)):
        spec.name = "y"  # type: ignore[misc]


def test_producer_spec_with_config_keys():
    from producers.base import ProducerSpec

    spec = ProducerSpec(
        name="takes",
        enabled_config_key="features.extract_takes",
        source_glob_config_key="limits.extract_takes_source_globs",
    )
    assert spec.enabled_config_key == "features.extract_takes"
    assert spec.source_glob_config_key == "limits.extract_takes_source_globs"


def test_producer_result_defaults():
    from producers.base import ProducerResult

    result = ProducerResult(producer="x", status="ok")
    assert result.producer == "x"
    assert result.status == "ok"
    assert result.reason is None
    assert result.outputs == ()


def test_producer_result_full():
    from producers.base import ProducerResult

    out = (Path("/tmp/a.md"), Path("/tmp/b.md"))
    result = ProducerResult(
        producer="suggestions",
        status="ok",
        reason=None,
        outputs=out,
    )
    assert result.outputs == out


def test_producer_result_is_frozen():
    from producers.base import ProducerResult

    result = ProducerResult(producer="x", status="ok")
    with pytest.raises((AttributeError, Exception)):
        result.status = "failed"  # type: ignore[misc]


def test_producer_result_status_values():
    """All three documented statuses construct cleanly."""
    from producers.base import ProducerResult

    for status in ("ok", "skipped", "failed"):
        ProducerResult(producer="x", status=status)  # type: ignore[arg-type]


# ── Registry: @register decorator ────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Each test gets a clean Registry — no leakage between tests."""
    from producers import base as producers_base

    saved = dict(producers_base._PRODUCERS)
    producers_base._PRODUCERS.clear()
    yield
    producers_base._PRODUCERS.clear()
    producers_base._PRODUCERS.update(saved)


def _make_producer(name: str, enabled_key: str | None = None, glob_key: str | None = None):
    """Build a minimally-conforming Producer class on the fly."""
    from producers.base import ProducerResult, ProducerSpec

    class _P:
        SPEC = ProducerSpec(
            name=name,
            enabled_config_key=enabled_key,
            source_glob_config_key=glob_key,
        )

        async def run(self, source: Path) -> ProducerResult:  # noqa: D401
            return ProducerResult(producer=name, status="ok")

    _P.__name__ = f"Producer_{name}"
    _P.__qualname__ = _P.__name__
    return _P


def test_register_adds_to_registry():
    from producers.base import _PRODUCERS, register

    cls = _make_producer("alpha")
    register(cls)

    assert "alpha" in _PRODUCERS
    assert _PRODUCERS["alpha"] is cls


def test_register_returns_class_unchanged():
    """@register must be usable as a decorator — returns the class."""
    from producers.base import register

    cls = _make_producer("alpha")
    returned = register(cls)
    assert returned is cls


def test_register_missing_spec_raises():
    from producers.base import register

    class _NoSpec:
        pass

    with pytest.raises(TypeError, match="SPEC"):
        register(_NoSpec)  # type: ignore[arg-type]


def test_register_duplicate_name_raises():
    from producers.base import register

    cls1 = _make_producer("dup")
    register(cls1)
    cls2 = _make_producer("dup")
    cls2.__qualname__ = "DifferentClass"
    with pytest.raises(ValueError, match="already registered"):
        register(cls2)


def test_register_same_class_reimport_is_noop():
    """A module run as __main__ then re-imported under its package path
    must not raise — Collector pattern, ported."""
    from producers.base import _PRODUCERS, register

    cls = _make_producer("twice")
    register(cls)
    # Same class, second call → no-op
    register(cls)
    assert len(_PRODUCERS) == 1


# ── Registry: enumeration ────────────────────────────────────────────


def test_all_producers_returns_instances_in_registration_order():
    from producers.base import all_producers, register

    register(_make_producer("first"))
    register(_make_producer("second"))
    register(_make_producer("third"))

    producers = all_producers()
    names = [p.SPEC.name for p in producers]
    assert names == ["first", "second", "third"]


def test_all_producers_returns_fresh_instances():
    """Each call yields new instances (mirrors Collector Registry)."""
    from producers.base import all_producers, register

    register(_make_producer("one"))
    a = all_producers()
    b = all_producers()
    assert a[0] is not b[0]


def test_get_producer_resolves_by_name():
    from producers.base import get_producer, register

    cls = _make_producer("findme")
    register(cls)

    p = get_producer("findme")
    assert p is not None
    assert p.SPEC.name == "findme"


def test_get_producer_returns_none_when_missing():
    from producers.base import get_producer

    assert get_producer("nonexistent") is None


# ── Protocol structural-conformance ─────────────────────────────────


def test_protocol_runtime_checkable():
    """A producer instance with SPEC + async run() satisfies the Protocol."""
    from producers.base import Producer

    cls = _make_producer("conforms")
    instance = cls()
    assert isinstance(instance, Producer)


def test_protocol_rejects_missing_run():
    """Plain class without `run` is not a Producer."""
    from producers.base import Producer, ProducerSpec

    class _NoRun:
        SPEC = ProducerSpec(name="x", enabled_config_key=None, source_glob_config_key=None)

    assert not isinstance(_NoRun(), Producer)
