"""Adapter-unit tests for the Apple HealthKit Export.xml streaming parser.

Schema verified live 2026-05-19 against an 11.5-year operator export (214 MB,
496k records). Fixture covers:
  - Body-composition latest-wins per day (BodyMass, BodyFatPercentage, ...)
  - Activity sum-per-day (StepCount, DistanceWalkingRunning, ...)
  - Unit normalisation (lb→kg, mi→km, kJ→kcal)
  - Workout extraction
  - Oura sourceName drop (no double-counting against the Oura API path)
  - Empty-day filtering
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.health.healthkit_xml import (
    HealthKitDailyAggregate,
    iter_aggregates,
    _day_of,
    _normalise,
    _UNIT_TO_KG,
    _UNIT_TO_KM,
)


# ── Fixture builder ──────────────────────────────────────────────────


_PROLOG = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<HealthData locale="en_US">'
    '<ExportDate value="2026-05-19 12:00:00 +0100"/>'
    '<Me HKCharacteristicTypeIdentifierDateOfBirth="1985-01-01"'
    ' HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"'
    ' HKCharacteristicTypeIdentifierBloodType="HKBloodTypeNotSet"'
    ' HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet"'
    ' HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse="None"/>'
)
_EPILOG = "</HealthData>"


def _make_export(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "Export.xml"
    p.write_text(_PROLOG + body + _EPILOG, encoding="utf-8")
    return p


def _rec(rtype: str, day: str, value: str, source: str = "iPhone",
         unit: str | None = None, hh: str = "08:00:00") -> str:
    unit_attr = f' unit="{unit}"' if unit else ""
    return (
        f'<Record type="{rtype}" sourceName="{source}"'
        f' startDate="{day} {hh} +0100"'
        f' endDate="{day} {hh} +0100"'
        f' value="{value}"{unit_attr}/>'
    )


def _workout(wtype: str, day: str, duration: str, distance: str | None = None,
             energy: str | None = None, source: str = "Watch") -> str:
    extra = ""
    if distance:
        extra += f' totalDistance="{distance}" totalDistanceUnit="km"'
    if energy:
        extra += f' totalEnergyBurned="{energy}" totalEnergyBurnedUnit="kcal"'
    return (
        f'<Workout workoutActivityType="HKWorkoutActivityType{wtype}"'
        f' duration="{duration}" durationUnit="min"{extra}'
        f' sourceName="{source}"'
        f' startDate="{day} 18:00:00 +0100"'
        f' endDate="{day} 18:35:00 +0100"/>'
    )


# ── _day_of / _normalise (pure helpers) ──────────────────────────────


def test_day_of_extracts_date_prefix():
    assert _day_of("2024-01-15 08:30:00 +0100") == "2024-01-15"
    assert _day_of("2024-01-15") == "2024-01-15"
    assert _day_of(None) is None
    assert _day_of("") is None
    assert _day_of("garbage") is None


def test_normalise_kg_from_lb():
    out = _normalise(176.0, "lb", _UNIT_TO_KG)
    assert out == pytest.approx(79.83, abs=0.1)


def test_normalise_km_from_mi():
    out = _normalise(3.0, "mi", _UNIT_TO_KM)
    assert out == pytest.approx(4.828, abs=0.01)


def test_normalise_unknown_unit_drops_record():
    assert _normalise(1.0, "furlongs", _UNIT_TO_KG) is None


def test_normalise_no_unit_passes_through():
    """StepCount / FlightsClimbed are unitless quantities — pass through."""
    assert _normalise(5000, None, _UNIT_TO_KG) == 5000


# ── iter_aggregates against synthetic fixtures ───────────────────────


def test_latest_wins_for_weight(tmp_path):
    body = (
        _rec("HKQuantityTypeIdentifierBodyMass", "2024-01-15", "70.5",
             source="Renpho", unit="kg", hh="07:00:00")
        + _rec("HKQuantityTypeIdentifierBodyMass", "2024-01-15", "71.2",
               source="Renpho", unit="kg", hh="20:00:00")
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert len(out) == 1
    assert out[0].day == "2024-01-15"
    assert out[0].weight_kg == 71.2  # later record wins


def test_steps_sum_excludes_oura(tmp_path):
    body = (
        _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "1000",
             source="iPhone")
        + _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "500",
               source="iPhone")
        + _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "9999",
               source="Oura")   # MUST be dropped
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert len(out) == 1
    assert out[0].steps_total == 1500


def test_distance_normalises_miles(tmp_path):
    body = _rec(
        "HKQuantityTypeIdentifierDistanceWalkingRunning",
        "2024-01-15", "3.0", source="iPhone", unit="mi",
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out[0].distance_km == pytest.approx(4.828, abs=0.01)


def test_weight_lb_normalises_to_kg(tmp_path):
    body = _rec(
        "HKQuantityTypeIdentifierBodyMass",
        "2024-01-15", "176.0", source="Renpho", unit="lb",
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out[0].weight_kg == pytest.approx(79.83, abs=0.1)


def test_workout_extracted_with_normalised_distance(tmp_path):
    body = _workout("Running", "2024-01-15", "35.2", distance="5.0", energy="320")
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert len(out) == 1
    assert out[0].workouts == [{
        "type": "Running",
        "start": "2024-01-15 18:00:00 +0100",
        "duration_min": 35.2,
        "distance_km": 5.0,
        "energy_kcal": 320,
    }]


def test_oura_workouts_dropped(tmp_path):
    body = _workout("Walking", "2024-01-15", "20.0", source="Oura")
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out == []  # no day emitted


def test_multi_day_grouping(tmp_path):
    body = (
        _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "5000")
        + _rec("HKQuantityTypeIdentifierStepCount", "2024-01-16", "6000")
        + _rec("HKQuantityTypeIdentifierBodyMass", "2024-01-15", "75.0",
               source="Renpho", unit="kg")
    )
    xml = _make_export(tmp_path, body)
    out = sorted(list(iter_aggregates(xml)), key=lambda a: a.day)
    assert [a.day for a in out] == ["2024-01-15", "2024-01-16"]
    assert out[0].steps_total == 5000
    assert out[0].weight_kg == 75.0
    assert out[1].steps_total == 6000
    assert out[1].weight_kg is None


def test_to_frontmatter_drops_none_fields(tmp_path):
    body = _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "500")
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    fm = out[0].to_frontmatter()
    assert fm == {"steps_total": 500}
    # NOT present: weight_kg / distance_km / workouts / sleep_hours
    assert "weight_kg" not in fm
    assert "workouts" not in fm


def test_empty_day_filtered(tmp_path):
    # Record with unknown type → ingested into a per-day bucket as
    # record_count++ but no field set → aggregate is empty → filtered out
    body = (
        '<Record type="HKQuantityTypeIdentifierUVExposure" sourceName="iPhone"'
        ' startDate="2024-01-15 08:00:00 +0100"'
        ' endDate="2024-01-15 08:00:00 +0100" value="1" unit="count"/>'
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out == []


def test_records_without_value_dropped(tmp_path):
    # Quantity records without a value can't be aggregated
    body = (
        '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone"'
        ' startDate="2024-01-15 08:00:00 +0100"'
        ' endDate="2024-01-15 08:00:00 +0100"/>'
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out == []


def test_body_fat_pct_fraction_to_percent(tmp_path):
    """Apple emits BodyFatPercentage as a fraction (0.196 unit=%) → render 19.6."""
    body = _rec(
        "HKQuantityTypeIdentifierBodyFatPercentage",
        "2024-01-15", "0.196", source="Renpho", unit="%",
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out[0].body_fat_pct == pytest.approx(19.6, abs=0.05)


def test_steps_integer_not_float(tmp_path):
    body = (
        _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "100")
        + _rec("HKQuantityTypeIdentifierStepCount", "2024-01-15", "50")
    )
    xml = _make_export(tmp_path, body)
    out = list(iter_aggregates(xml))
    assert out[0].steps_total == 150
    assert isinstance(out[0].steps_total, int)
