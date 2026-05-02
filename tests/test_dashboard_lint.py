"""Pure-function tests for `dashboard_lint` rendering + write helpers.

Mirror of `test_dashboard_stats.py` -- live counters (`compute_lint_data`)
are smoke-verified at the slice-level CLI test, not here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _base_data(**overrides) -> dict:
    data = {
        "orphans_count": 3,
        "stale_count": 7,
        "missing_backlinks_count": 1,
        "failed_flushes_count": 2,
        "orphans": [
            {"link": "knowledge/concepts/foo", "detail": "never linked from index"},
            {"link": "knowledge/projects/bar", "detail": "never linked from index"},
            {"link": "knowledge/concepts/baz", "detail": "never linked from index"},
        ],
        "stale": [
            {"link": "knowledge/concepts/old", "detail": "last touched 2026-01-01 (120d ago)"},
        ] * 7,
        "missing_backlinks": [
            {"link": "knowledge/concepts/foo", "detail": "links [[bar]] but [[bar]] doesn't link back"},
        ],
        "failed_flushes": [
            {"link": "scripts/sessions/failed-flushes/2026-04-29T1812.md", "detail": "TimeoutError"},
            {"link": "scripts/sessions/failed-flushes/2026-04-30T0901.md", "detail": "JSONDecodeError"},
        ],
        "last_updated_ts": "2026-05-02T22:30:00+02:00",
    }
    data.update(overrides)
    return data


def test_render_body_has_all_four_sections() -> None:
    import dashboard_lint

    body = dashboard_lint.render_body(_base_data())
    assert "## Orphans" in body
    assert "## Stale" in body
    assert "## Missing backlinks" in body
    assert "## Failed flushes" in body


def test_render_body_renders_each_issue_as_wikilink_with_detail() -> None:
    import dashboard_lint

    body = dashboard_lint.render_body(_base_data())
    assert "- [[knowledge/concepts/foo]] — never linked from index" in body
    assert "- [[scripts/sessions/failed-flushes/2026-04-29T1812.md]] — TimeoutError" in body


def test_render_body_empty_queue_still_renders_header() -> None:
    """Empty section must still render its `## Title` so embeds resolve."""
    import dashboard_lint

    data = _base_data(orphans_count=0, orphans=[])
    body = dashboard_lint.render_body(data)
    assert "## Orphans" in body
    orphans_idx = body.index("## Orphans")
    stale_idx = body.index("## Stale")
    between = body[orphans_idx:stale_idx]
    assert "- [[" not in between


def test_write_dashboard_lint_frontmatter_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dashboard_lint

    output = tmp_path / "_dashboard-lint.md"
    monkeypatch.setattr(dashboard_lint, "OUTPUT_FILE", output)

    data = _base_data()
    body = dashboard_lint.render_body(data)
    written = dashboard_lint.write_dashboard_lint(data, body)

    assert written == output
    content = output.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "orphans_count: 3" in content
    assert "stale_count: 7" in content
    assert "missing_backlinks_count: 1" in content
    assert "failed_flushes_count: 2" in content
    assert "last_updated_ts: 2026-05-02T22:30:00+02:00" in content
    assert "## Orphans" in content


def test_write_dashboard_lint_truncates_long_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue detail strings longer than ~120 chars get truncated to keep lines scannable."""
    import dashboard_lint

    output = tmp_path / "_dashboard-lint.md"
    monkeypatch.setattr(dashboard_lint, "OUTPUT_FILE", output)

    long_detail = "x" * 500
    data = _base_data(orphans=[{"link": "knowledge/foo", "detail": long_detail}], orphans_count=1)
    body = dashboard_lint.render_body(data)
    dashboard_lint.write_dashboard_lint(data, body)

    content = output.read_text(encoding="utf-8")
    assert "x" * 500 not in content
    assert "…" in content or "..." in content
