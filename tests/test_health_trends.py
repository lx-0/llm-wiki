"""Deterministic health-trend synthesis logic. No LLM involved."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _day(health: Path, date: str, **metrics) -> None:
    fm = [f"---", f"title: Health — {date}", "type: health-rollup", f"date: '{date}'",
          "sources:", "- healthkit"]
    for k, v in metrics.items():
        fm.append(f"{k}: {v}")
    fm += ["sensitivity: high", "---", "", f"# Health — {date}", "", "(Add observations below as needed.)"]
    (health / f"{date}--default.md").write_text("\n".join(fm), encoding="utf-8")


def test_collect_metrics_numeric_only_and_sorted(tmp_path):
    import health_trends as ht
    h = tmp_path / "health"; h.mkdir()
    _day(h, "2026-02-02", distance_km=3.0, steps=2000)
    _day(h, "2026-01-01", distance_km=2.0)            # earlier
    _day(h, "2026-02-01", distance_km=4.0, steps="oops")  # non-numeric steps ignored
    series, days, span = ht.collect_metrics(h)
    assert days == 3
    assert span == ("2026-01-01", "2026-02-02")
    # distance_km from all 3, sorted by date; steps only the one numeric value
    assert [d for d, _ in series["distance_km"]] == ["2026-01-01", "2026-02-01", "2026-02-02"]
    assert series["steps"] == [("2026-02-02", 2000.0)]
    # bookkeeping keys never become metrics
    assert "sensitivity" not in series and "date" not in series and "sources" not in series


def test_render_block_coverage_filter_and_sentinels(tmp_path, monkeypatch):
    import health_trends as ht
    monkeypatch.setattr(ht.CONFIG.limits, "health_trends_min_coverage_days", 3)
    monkeypatch.setattr(ht.CONFIG.limits, "health_trends_recent_months", 6)
    h = tmp_path / "health"; h.mkdir()
    for i in range(5):
        _day(h, f"2026-01-0{i+1}", distance_km=float(i + 1), weight_kg=70.0)
    _day(h, "2026-01-09", rare_metric=99.0)  # only 1 day → below min coverage → dropped
    block = ht.render_block(h)
    assert block.startswith(ht.BEGIN) and block.rstrip().endswith(ht.END)
    assert "## Trends" in block
    assert "`distance_km`" in block and "`weight_kg`" in block
    assert "rare_metric" not in block  # coverage filter


def test_upsert_block_creates_replaces_and_preserves_backlinks(tmp_path):
    import health_trends as ht
    page = tmp_path / "health.md"
    # 1. create-if-absent
    out = ht._upsert_block(page, ht.BEGIN + "\nX\n" + ht.END)
    assert "type: concept" in out and ht.BEGIN in out
    page.write_text(out, encoding="utf-8")
    # add a backlinks footer to verify the block lands BEFORE it
    page.write_text(out.rstrip() + "\n\n<!-- backlinks:begin -->\n\n## Backlinks\n\n<!-- backlinks:end -->\n", encoding="utf-8")
    # 2. replace existing block idempotently
    out2 = ht._upsert_block(page, ht.BEGIN + "\nY-NEW\n" + ht.END)
    assert "Y-NEW" in out2 and "X" not in out2
    assert out2.count(ht.BEGIN) == 1  # not duplicated
    assert "<!-- backlinks:begin -->" in out2  # footer preserved
    assert out2.index(ht.BEGIN) < out2.index("<!-- backlinks:begin -->")  # trends before backlinks


def test_trend_arrow_direction(tmp_path, monkeypatch):
    import health_trends as ht
    # rising series across two 1-month windows (recent_months=1)
    vals = [(f"2026-01-0{i+1}", 10.0) for i in range(3)] + [(f"2026-02-0{i+1}", 20.0) for i in range(3)]
    assert ht._trend_arrow(vals, recent_months=1) == "↑"
    falling = [(f"2026-01-0{i+1}", 20.0) for i in range(3)] + [(f"2026-02-0{i+1}", 10.0) for i in range(3)]
    assert ht._trend_arrow(falling, recent_months=1) == "↓"
    assert ht._trend_arrow([("2026-01-01", 1.0)], recent_months=6) == "·"  # too little data
