"""Pure-function tests for `dashboard_stats` rendering + write helpers.

Path-dependent counters (`compute_stats`) are not covered here -- they use
config.ROOT_DIR / list_raw_files / list_wiki_articles which would require
mocking the entire engine path-resolution. Verification of those happens at
the slice-level CLI smoke test (running `dashboard_stats.py` against a real
vault and inspecting `_dashboard-stats.md`).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _base_stats(**overrides) -> dict:
    stats = {
        "pending_compiles": 5,
        "failed_flushes": 0,
        "lint_warnings": 12,
        "total_tokens_lifetime": 1234567,
        "articles_total": 263,
        "daily_logs_total": 47,
        "open_commitments": 0,
        "entities_with_action_items": 0,
        "last_compile_ts": "2026-05-02T16:00:00+00:00",
        "generated_at": "2026-05-02T17:00:00+00:00",
    }
    stats.update(overrides)
    return stats


def test_render_callout_includes_all_fields() -> None:
    from dashboard import dashboard_stats

    callout = dashboard_stats.render_callout(_base_stats())
    assert "Pipeline status" in callout
    assert "**Pending compiles:** 5" in callout
    assert "**Failed flushes:** 0" in callout
    assert "**Lint warnings:** 12" in callout
    assert "**LLM tokens (lifetime):** 1,234,567" in callout
    assert "**Articles:** 263" in callout
    assert "**Daily logs:** 47" in callout


def test_render_callout_traffic_lights() -> None:
    from dashboard import dashboard_stats

    green = dashboard_stats.render_callout(
        _base_stats(pending_compiles=0, failed_flushes=0, lint_warnings=0)
    )
    assert green.count("🟢") >= 3

    yellow = dashboard_stats.render_callout(_base_stats(pending_compiles=5, lint_warnings=5))
    assert "🟡" in yellow

    red = dashboard_stats.render_callout(
        _base_stats(pending_compiles=50, failed_flushes=2, lint_warnings=25)
    )
    assert red.count("🔴") >= 3


def test_write_dashboard_stats_frontmatter_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dashboard import dashboard_stats

    output = tmp_path / "_dashboard-stats.md"
    monkeypatch.setattr(dashboard_stats, "OUTPUT_FILE", output)

    stats = _base_stats()
    callout = dashboard_stats.render_callout(stats)
    written = dashboard_stats.write_dashboard_stats(stats, callout)

    assert written == output
    content = output.read_text(encoding="utf-8")

    # frontmatter
    assert content.startswith("---\n")
    assert "pending_compiles: 5" in content
    assert "failed_flushes: 0" in content
    assert "lint_warnings: 12" in content
    # No dollar field: token accounting is the metering surface
    # (DECISIONS 2026-05-23); the old lifetime figure was frozen for compile
    # and still creeping from queries, i.e. wrong in both directions.
    assert "total_cost_lifetime" not in content
    assert "total_tokens_lifetime: 1234567" in content
    assert "articles_total: 263" in content
    assert "daily_logs_total: 47" in content
    assert "last_compile_ts: 2026-05-02T16:00:00+00:00" in content

    # body has callout
    assert "Pipeline status" in content


def test_write_dashboard_stats_handles_null_compile_ts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh vault (no compiled articles) writes `last_compile_ts: null`."""
    from dashboard import dashboard_stats

    output = tmp_path / "_dashboard-stats.md"
    monkeypatch.setattr(dashboard_stats, "OUTPUT_FILE", output)

    stats = _base_stats(last_compile_ts=None)
    callout = dashboard_stats.render_callout(stats)
    dashboard_stats.write_dashboard_stats(stats, callout)

    content = output.read_text(encoding="utf-8")
    assert "last_compile_ts: null" in content
    assert "**Last compile:** never" in content
