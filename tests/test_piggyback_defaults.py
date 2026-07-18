"""Piggyback-defaults single-source parity (C05).

`core.config_schema._default_piggybacks` is the ONE source of piggyback
defaults. Historically it was double-tabled against each collector's
`CollectorSpec.piggyback_cooldown_hours` with per-name-divergent precedence:
7 of 9 piggyback-default collectors resolved their cooldown from the defaults
table, while email (whose defaults entry was the zombie `email_incremental`
key nothing read) and health (no entry at all) silently fell through to the
SPEC value. These tests pin the collapsed state:

- every piggyback-default collector has a defaults entry named exactly
  `SPEC.name` with the SAME cooldown as its SPEC declaration (so the SPEC
  fallback in `build_piggyback_tasks` is provably dead for shipped
  collectors),
- every defaults entry has a real consumer (Registry collector or built-in
  task) — no zombie names,
- `max_per_run` only appears where a consumer actually reads it.
"""

from __future__ import annotations

from collectors.base import all_collectors
from core import piggybacks
from core.config_schema import _default_piggybacks


def _registry_piggyback_specs() -> dict[str, int]:
    """SPEC.name → SPEC.piggyback_cooldown_hours for piggyback-default collectors.

    Uses the STATIC declaration (all_collectors + SPEC.piggyback_default), not
    `piggyback_collectors()` — that helper additionally filters by
    `is_configured()`, which depends on the test environment's CONFIG.
    """
    import collectors  # noqa: F401  — imports all submodules → registration

    return {
        c.SPEC.name: c.SPEC.piggyback_cooldown_hours
        for c in all_collectors()
        if c.SPEC.piggyback_default
    }


def test_registry_collector_defaults_parity():
    """Name-by-name: every piggyback-default collector has a defaults entry
    whose cooldown equals its SPEC declaration."""
    defaults = _default_piggybacks()
    specs = _registry_piggyback_specs()
    assert specs, "registry discovery returned no piggyback-default collectors"
    for name, spec_cooldown in sorted(specs.items()):
        assert name in defaults, (
            f"collector {name!r} (piggyback_default=True) has no "
            "_default_piggybacks entry — add one with cooldown_hours == "
            "SPEC.piggyback_cooldown_hours (core/config_schema.py)"
        )
        assert defaults[name].cooldown_hours == spec_cooldown, (
            f"piggyback default for {name!r} diverges: _default_piggybacks says "
            f"{defaults[name].cooldown_hours}h, SPEC says {spec_cooldown}h — "
            "one source of truth, keep them equal"
        )


def test_no_zombie_default_names():
    """Every defaults entry is consumed by a Registry collector or a built-in
    task lookup — the guard that would have caught `email_incremental`."""
    defaults = set(_default_piggybacks())
    consumers = set(_registry_piggyback_specs()) | set(piggybacks._BUILTIN_PIGGYBACK_TASKS)
    zombies = defaults - consumers
    assert not zombies, (
        f"_default_piggybacks entries {sorted(zombies)} match no collector "
        "SPEC.name and no _BUILTIN_PIGGYBACK_TASKS key — nothing will ever "
        "read them (zombie knobs advertised by `wiki config keys`)"
    )


def test_deliberately_absent_builtin_tasks_stay_absent():
    """concept_reconcile + health_trends are double-gated: their defaults-table
    ABSENCE is the off-switch (build_piggyback_tasks skips built-ins without a
    CONFIG.piggybacks block). Adding a defaults entry would silently enable
    them for every vault."""
    defaults = set(_default_piggybacks())
    assert "concept_reconcile" not in defaults
    assert "health_trends" not in defaults


def test_max_per_run_only_where_consumed():
    """Registry-collector entries carry max_per_run only where the collector
    itself reads it (screenshots, pictures). jamie/gmeet/calendar caps live in
    limits.*_max_per_run + per-account sub-blocks — a max_per_run here would
    be a dead knob (the registry spawn path never passes it)."""
    defaults = _default_piggybacks()
    registry_names = set(_registry_piggyback_specs())
    with_cap = {
        name for name in registry_names
        if name in defaults and defaults[name].max_per_run is not None
    }
    assert with_cap == {"screenshots", "pictures"}, (
        f"registry collectors with a max_per_run default: {sorted(with_cap)} — "
        "expected exactly screenshots + pictures (the self-capping ones)"
    )
