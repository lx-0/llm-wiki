"""`wiki doctor` must notice a broken virtualenv.

Live incident 2026-08-26: the operator's vault venv held *partially
materialized* packages — `httpx` without its `_transports/` subpackage,
`claude_agent_sdk` without `mcp.client`, `prompt_toolkit` without a submodule.
Version metadata intact, most modules importable, but `import httpx` raised.
That takes down every HTTP surface plus compile / flush / dream / publish at
once, and it surfaced only as a piggyback exiting non-zero with no stderr
(the runner routes child output to DEVNULL). Nothing in doctor looked.

The dependency list is DERIVED from pyproject.toml — hand-maintaining a second
copy is the "fourth hand registry" mistake that already bit the config loader
(KNOWLEDGE.md 2026-08-25). Only the distribution→import-name exceptions are data.
"""

from __future__ import annotations

import core.health as health


def test_declared_dependencies_all_resolve_to_an_import_name():
    """Every distribution in pyproject.toml maps to something importable —
    guards the exceptions table against drifting when a dep is added."""
    names = health._declared_import_names()
    assert names, "no dependencies parsed from pyproject.toml"
    # Spot-check the mappings that are NOT identity, i.e. the ones a future
    # dependency bump can silently break.
    assert "yaml" in names          # pyyaml
    assert "dotenv" in names        # python-dotenv
    assert "PIL" in names           # pillow
    assert "claude_agent_sdk" in names
    assert "yt_dlp" in names
    # And that no raw distribution name leaked through unmapped.
    for bad in ("pyyaml", "python-dotenv", "pillow", "claude-agent-sdk", "yt-dlp"):
        assert bad not in names, f"{bad} reached the import list unmapped"


def test_healthy_environment_reports_ok(monkeypatch):
    monkeypatch.setattr(health, "_failed_imports", lambda names: [])
    r = health.check_dependencies_importable()
    assert r.severity == "ok"


def test_broken_package_is_critical_and_names_it(monkeypatch):
    """A partially materialized package is not a warning — the engine cannot
    run at all, so it must outrank everything else in the banner."""
    monkeypatch.setattr(
        health, "_failed_imports",
        lambda names: [("httpx", "ModuleNotFoundError: No module named 'httpx._transports'")],
    )
    r = health.check_dependencies_importable()
    assert r.severity == "critical"
    assert "httpx" in r.message
    assert "uv sync" in (r.fix or "")


def test_several_failures_are_summarised_not_dumped(monkeypatch):
    monkeypatch.setattr(
        health, "_failed_imports",
        lambda names: [(f"pkg{i}", "ModuleNotFoundError: boom") for i in range(9)],
    )
    r = health.check_dependencies_importable()
    assert r.severity == "critical"
    assert "9" in r.message
    assert len(r.message) < 300, "banner line must stay readable"
    assert r.details and len(r.details.get("failed", [])) == 9


def test_quick_mode_skips(monkeypatch):
    def _boom(_names):
        raise AssertionError("must not spawn a subprocess in --quick mode")

    monkeypatch.setattr(health, "_failed_imports", _boom)
    r = health.check_dependencies_importable(quick=True)
    assert r.severity == "info"


def test_probe_survives_an_unreadable_pyproject(monkeypatch):
    """Doctor must never crash — a missing/garbled manifest degrades to a
    reported probe failure, not a traceback."""
    def _boom():
        raise OSError("pyproject gone")

    monkeypatch.setattr(health, "_declared_import_names", _boom)
    r = health.check_dependencies_importable()
    assert r.severity in ("warning", "info")


def test_probe_actually_catches_a_broken_import():
    """The mechanism itself, unmocked: a package whose top-level import raises
    is reported with its error. This is the shape the incident had — the
    distribution is 'there', the import is not."""
    failures = _failed_imports_for(["json", "httpx.this_submodule_does_not_exist"])
    assert [n for n, _ in failures] == ["httpx.this_submodule_does_not_exist"]
    assert "ModuleNotFoundError" in failures[0][1]


def _failed_imports_for(names):
    return health._failed_imports(names)


def test_real_environment_imports_cleanly():
    """Integration: the dev checkout's own venv must pass its own check. This
    is the assertion that would have gone red on the operator's vault."""
    failures = health._failed_imports(health._declared_import_names())
    assert failures == [], f"broken packages in this environment: {failures}"
