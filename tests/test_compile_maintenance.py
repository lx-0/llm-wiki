"""compile.py drains due maintenance at the end of a real compile.

The operator lives in `wiki update && wiki compile` and rarely flushes, so the
flush-only / after-18:00 piggyback trigger never fired for them and every
maintenance queue piled up. `_spawn_maintenance` closes that gap: a real
(non-dry-run) compile spawns the due piggybacks itself, bypassing the hour gate
(cooldown still rate-limits), unless the operator disables
`scheduling.piggybacks_on_compile`.
"""

from __future__ import annotations

import compile as compile_mod


def test_spawn_maintenance_fires_when_knob_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(compile_mod, "run_due_piggybacks", lambda **kw: calls.append(kw) or [])
    monkeypatch.setattr(compile_mod.CONFIG.scheduling, "piggybacks_on_compile", True, raising=False)

    compile_mod._spawn_maintenance()

    assert len(calls) == 1
    assert calls[0]["ignore_hour_gate"] is True  # daytime compiles must still drain


def test_spawn_maintenance_skipped_when_knob_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(compile_mod, "run_due_piggybacks", lambda **kw: calls.append(kw) or [])
    monkeypatch.setattr(compile_mod.CONFIG.scheduling, "piggybacks_on_compile", False, raising=False)

    compile_mod._spawn_maintenance()

    assert calls == []


def test_spawn_maintenance_never_raises(monkeypatch):
    """A piggyback-spawn failure must never abort the compile that triggered it."""
    def boom(**kw):
        raise RuntimeError("spawn exploded")

    monkeypatch.setattr(compile_mod, "run_due_piggybacks", boom)
    monkeypatch.setattr(compile_mod.CONFIG.scheduling, "piggybacks_on_compile", True, raising=False)

    compile_mod._spawn_maintenance()  # must not raise
