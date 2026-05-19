"""Tests for `_merge_healthkit_into_path` — the per-day file create/merge helper.

Covers:
  - Fresh file creation (no Oura predecessor)
  - Merge into existing Oura file (Oura wins on overlap, sources unioned)
  - Idempotency on second call with same aggregate
  - Frontmatter ordering (identity → sources → Oura → HealthKit)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from collectors.health import _merge_healthkit_into_path
from adapters.health.healthkit_xml import HealthKitDailyAggregate


def _agg(day: str = "2024-01-15", **kw) -> HealthKitDailyAggregate:
    a = HealthKitDailyAggregate(day=day)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, fm_block, _ = text.split("---", 2)
    return yaml.safe_load(fm_block)


def test_creates_fresh_file_when_target_missing(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    agg = _agg(weight_kg=75.5, steps_total=8000)
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is True
    assert target.exists()
    fm = _read_fm(target)
    assert fm["title"] == "Health — 2024-01-15"
    assert fm["type"] == "health-rollup"
    assert fm["date"] == "2024-01-15"
    assert fm["account"] == "default"
    assert fm["sources"] == ["healthkit"]
    assert fm["weight_kg"] == 75.5
    assert fm["steps_total"] == 8000
    assert fm["sensitivity"] == "high"


def test_merge_into_oura_file_preserves_oura_keys(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    target.write_text(
        "---\n"
        "title: Health — 2024-01-15\n"
        "type: health-rollup\n"
        "date: '2024-01-15'\n"
        "account: default\n"
        "sources:\n- oura\n"
        "sleep_hours: 7.5\n"
        "sleep_score: 80\n"
        "hrv_overnight: 45\n"
        "steps: 6000\n"
        "resting_hr: 55\n"
        "sensitivity: high\n"
        "---\n\n# Health — 2024-01-15\n\n(Add observations below.)\n",
        encoding="utf-8",
    )
    agg = _agg(
        weight_kg=75.5,
        steps_total=8000,  # HealthKit steps DIFFER from Oura steps; both keys
                           # live side-by-side (Oura wins for `steps`, HealthKit
                           # adds `steps_total`).
        body_fat_pct=18.2,
        workouts=[{"type": "Running", "duration_min": 30.0}],
    )
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is True

    fm = _read_fm(target)
    # Oura keys preserved verbatim
    assert fm["sleep_hours"] == 7.5
    assert fm["sleep_score"] == 80
    assert fm["hrv_overnight"] == 45
    assert fm["steps"] == 6000           # Oura wins on overlap
    assert fm["resting_hr"] == 55
    # HealthKit keys added
    assert fm["weight_kg"] == 75.5
    assert fm["steps_total"] == 8000     # HealthKit-only key
    assert fm["body_fat_pct"] == 18.2
    assert fm["workouts"] == [{"type": "Running", "duration_min": 30.0}]
    # Sources unioned
    assert fm["sources"] == ["oura", "healthkit"]


def test_idempotent_second_call_no_change(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    agg = _agg(weight_kg=75.5, steps_total=8000)
    _merge_healthkit_into_path(target, agg, account_id="default")
    first_bytes = target.read_bytes()
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is False
    assert target.read_bytes() == first_bytes


def test_empty_aggregate_skipped(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    agg = _agg()  # no fields set
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is False
    assert not target.exists()


def test_frontmatter_key_order_is_stable(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    agg = _agg(weight_kg=75.5, steps_total=8000, body_fat_pct=18.0,
               workouts=[{"type": "Walking"}])
    _merge_healthkit_into_path(target, agg, account_id="default")
    text = target.read_text(encoding="utf-8")
    lines = [l for l in text.split("\n") if ":" in l and not l.startswith(" ")]
    keys = [l.split(":", 1)[0] for l in lines]
    # title precedes type; sources precedes any metric; HealthKit keys grouped
    assert keys.index("title") < keys.index("type")
    assert keys.index("sources") < keys.index("weight_kg")
    assert keys.index("weight_kg") < keys.index("steps_total")
    # sensitivity at the end
    assert keys.index("sensitivity") == len(keys) - 1


def test_merge_adds_healthkit_when_oura_file_missing_sources(tmp_path):
    """Edge case: legacy Oura file without `sources:` key still gets healthkit added."""
    target = tmp_path / "2024-01-15--default.md"
    target.write_text(
        "---\n"
        "title: Health — 2024-01-15\n"
        "type: health-rollup\n"
        "date: '2024-01-15'\n"
        "account: default\n"
        "sleep_hours: 7.5\n"
        "sensitivity: high\n"
        "---\n\n# Health — 2024-01-15\n",
        encoding="utf-8",
    )
    agg = _agg(weight_kg=75.5)
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is True
    fm = _read_fm(target)
    assert fm["sources"] == ["healthkit"]
    assert fm["weight_kg"] == 75.5
    assert fm["sleep_hours"] == 7.5  # legacy Oura key preserved


def test_unparseable_frontmatter_is_rebuilt(tmp_path):
    target = tmp_path / "2024-01-15--default.md"
    target.write_text(
        "---\n:::not yaml:::\n---\nbody preserved\n",
        encoding="utf-8",
    )
    agg = _agg(weight_kg=75.5)
    changed = _merge_healthkit_into_path(target, agg, account_id="default")
    assert changed is True
    fm = _read_fm(target)
    assert fm["weight_kg"] == 75.5
    assert fm["sources"] == ["healthkit"]
