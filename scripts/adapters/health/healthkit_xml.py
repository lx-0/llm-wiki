"""Apple Health `Export.xml` streaming parser → per-day aggregates.

Phase 2 of the health-collector pitch (`.ytstack/backlog/shipped/health-collector.md`).

Wire shape (verified live 2026-05-19 against an 11.5-year operator export):

    <HealthData locale="en_US">
      <ExportDate value="..."/>
      <Me .../>
      <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Renpho"
              startDate="2024-01-15 08:30:00 +0100" endDate="..."
              value="78.5" unit="kg"/>
      <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone"
              startDate="..." value="1234"/>
      <Workout workoutActivityType="HKWorkoutActivityTypeWalking"
               duration="35.2" durationUnit="min" totalDistance="2.4"
               totalDistanceUnit="km" totalEnergyBurned="180"
               totalEnergyBurnedUnit="kcal" sourceName="..."
               startDate="..." endDate="..."/>
      ...
    </HealthData>

Apple writes startDate in the device's local timezone at recording time
(e.g. "2024-01-15 08:30:00 +0100") — the date portion before the space is
the operator's wall-clock day and is what humans expect when grouping
"daily" metrics. We bucket by that prefix, not by re-zoning to UTC.

CRITICAL — Oura double-counting: the operator's Oura ring also writes
into HealthKit (sourceName="Oura", 126k records observed). The Oura
adapter already pulls those metrics via the API for the last 90 days.
The parser drops sourceName="Oura" records from steps/distance/energy
aggregation so re-runs over an export that overlaps the API window don't
double-count. Pre-Oura history (years before the ring) carries no Oura
records, so the long-tail timeline expands cleanly.

The parser is pure: no I/O beyond reading the supplied XML path, no
network, no clock. Aggregation runs in O(records) with bounded memory
via `iterparse(events=("end",))` + `el.clear()` — a 214 MB file with
~500k records peaks under 80 MB RSS in CPython.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

# sourceName values whose records mirror the Oura API and must NOT be
# re-aggregated into HealthKit's per-day totals (Oura adapter owns them).
_OURA_SOURCE_NAMES: frozenset[str] = frozenset({"Oura"})

# Type prefix Apple uses on quantity / category record types.
_QTY = "HKQuantityTypeIdentifier"
_CAT = "HKCategoryTypeIdentifier"
_WORKOUT_PREFIX = "HKWorkoutActivityType"

# Records we aggregate. Anything not listed here is skipped during the
# stream pass — keeps memory bounded and tests focused.
_TYPES_LATEST = {  # last-value-wins per day (body composition)
    f"{_QTY}BodyMass": "weight_kg",
    f"{_QTY}BodyFatPercentage": "body_fat_pct",
    f"{_QTY}LeanBodyMass": "lean_body_mass_kg",
    f"{_QTY}BodyMassIndex": "bmi",
    f"{_QTY}RestingHeartRate": "resting_hr",
    f"{_QTY}Height": "height_cm",
}
_TYPES_SUM = {  # sum-per-day (activity/exposure)
    f"{_QTY}StepCount": "steps_total",
    f"{_QTY}DistanceWalkingRunning": "distance_km",
    f"{_QTY}ActiveEnergyBurned": "active_energy_kcal",
    f"{_QTY}BasalEnergyBurned": "basal_energy_kcal",
    f"{_QTY}FlightsClimbed": "flights_climbed",
}

# Unit normalisation — Apple emits units alongside each Record. We don't
# trust callers; we always normalise to one canonical unit before sum/avg.
_UNIT_TO_KG = {"kg": 1.0, "lb": 0.453_592_37, "g": 0.001, "stone": 6.350_29}
_UNIT_TO_KM = {"km": 1.0, "mi": 1.609_344, "m": 0.001, "ft": 0.000_304_8}
_UNIT_TO_CM = {"cm": 1.0, "m": 100.0, "in": 2.54, "ft": 30.48}
_UNIT_TO_KCAL = {"kcal": 1.0, "Cal": 1.0, "cal": 0.001, "kJ": 0.239_006}

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# ── Per-day aggregate ────────────────────────────────────────────────


@dataclass
class HealthKitDailyAggregate:
    """One day's HealthKit-side metrics. All fields optional; the collector
    drops keys with `None`/empty values before merging into frontmatter."""

    day: str  # YYYY-MM-DD
    # Body composition — last-value-wins per day
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    lean_body_mass_kg: float | None = None
    bmi: float | None = None
    resting_hr: int | None = None
    height_cm: float | None = None
    # Activity — sum per day
    steps_total: int | None = None
    distance_km: float | None = None
    active_energy_kcal: float | None = None
    basal_energy_kcal: float | None = None
    flights_climbed: int | None = None
    # Workouts that day (zero or more)
    workouts: list[dict] = field(default_factory=list)
    # Provenance / debugging
    record_count: int = 0
    sources: set[str] = field(default_factory=set)

    def to_frontmatter(self) -> dict:
        """Stable, ordered dict of NON-EMPTY keys for YAML emission.

        Drops `None`/empty so frontmatter stays clean. The collector merges
        this dict into the per-day file's frontmatter (Oura keys win when both
        sources cover the same field — sleep/HRV/scores; HealthKit fills the
        rest).
        """
        out: dict = {}
        for k in (
            "weight_kg", "body_fat_pct", "lean_body_mass_kg", "bmi",
            "resting_hr", "height_cm",
            "steps_total", "distance_km", "active_energy_kcal",
            "basal_energy_kcal", "flights_climbed",
        ):
            v = getattr(self, k)
            if v is not None:
                # round float results so YAML doesn't emit 17 decimal digits
                if isinstance(v, float):
                    v = round(v, 2)
                out[k] = v
        if self.workouts:
            out["workouts"] = self.workouts
        return out

    def is_empty(self) -> bool:
        return not self.to_frontmatter()


# ── Helpers (pure) ────────────────────────────────────────────────────


def _day_of(attr_start_date: str | None) -> str | None:
    """Apple writes startDate as 'YYYY-MM-DD HH:MM:SS +ZZZZ' — first 10 chars."""
    if not attr_start_date:
        return None
    m = _DATE_RE.match(attr_start_date)
    return m.group(1) if m else None


def _to_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalise(value: float, unit: str | None, table: dict[str, float]) -> float | None:
    """Multiply value by unit→canonical factor; unknown unit → None (skip record)."""
    if unit is None:
        # Some Records omit unit on numeric quantities (counts: StepCount,
        # FlightsClimbed). For count-style types the canonical "unit" is 1.
        return value
    f = table.get(unit)
    if f is None:
        log.debug("healthkit: unknown unit %r — dropping record", unit)
        return None
    return value * f


# ── Streaming parse ──────────────────────────────────────────────────


def iter_aggregates(
    xml_path: Path,
    *,
    drop_sources: frozenset[str] = _OURA_SOURCE_NAMES,
) -> Iterator[HealthKitDailyAggregate]:
    """Stream `xml_path`, emit one HealthKitDailyAggregate per day with data.

    Records whose `sourceName` is in `drop_sources` (default: Oura) are
    excluded — the Oura adapter owns those days via its API path. Pre-Oura
    history is unaffected.

    Memory: O(distinct-days). Per-record state is cleared after each `end`
    event via `el.clear()` — RSS stays bounded on multi-GB exports.
    """
    by_day: dict[str, HealthKitDailyAggregate] = {}

    for ev, el in ET.iterparse(str(xml_path), events=("end",)):
        if el.tag == "Record":
            _ingest_record(el, by_day, drop_sources)
            el.clear()
        elif el.tag == "Workout":
            _ingest_workout(el, by_day, drop_sources)
            el.clear()
        elif el.tag in ("MetadataEntry", "HeartRateVariabilityMetadataList",
                        "WorkoutEvent", "WorkoutRoute", "WorkoutStatistics",
                        "Correlation", "ActivitySummary"):
            # Drop the noise children early so they don't accumulate.
            el.clear()

    for agg in by_day.values():
        if agg.is_empty() and not agg.workouts:
            continue
        yield agg


def _ingest_record(
    el: ET.Element,
    by_day: dict[str, HealthKitDailyAggregate],
    drop_sources: frozenset[str],
) -> None:
    rtype = el.get("type")
    if rtype is None:
        return
    source = el.get("sourceName") or ""
    if source in drop_sources:
        return
    day = _day_of(el.get("startDate"))
    if day is None:
        return
    value = _to_float(el.get("value"))
    if value is None and rtype not in (f"{_CAT}SleepAnalysis",):
        # Category records carry value="HKCategoryValueSleepAnalysis..." (string).
        # Quantity records without a numeric value are unusable.
        return
    unit = el.get("unit")

    agg = by_day.get(day)
    if agg is None:
        agg = HealthKitDailyAggregate(day=day)
        by_day[day] = agg
    agg.record_count += 1
    if source:
        agg.sources.add(source)

    if rtype in _TYPES_LATEST:
        field_name = _TYPES_LATEST[rtype]
        canonical = _normalised_for_field(field_name, value, unit)
        if canonical is None:
            return
        # last-value-wins per day — Apple emits in chronological order within
        # a source, so the final write for the day is the most-recent reading.
        setattr(agg, field_name, _maybe_int(field_name, canonical))
        return

    if rtype in _TYPES_SUM:
        field_name = _TYPES_SUM[rtype]
        canonical = _normalised_for_field(field_name, value, unit)
        if canonical is None:
            return
        current = getattr(agg, field_name) or 0
        setattr(agg, field_name, _maybe_int(field_name, current + canonical))
        return

    # Unhandled type — silently skip; the type catalog is intentionally narrow.


def _ingest_workout(
    el: ET.Element,
    by_day: dict[str, HealthKitDailyAggregate],
    drop_sources: frozenset[str],
) -> None:
    source = el.get("sourceName") or ""
    if source in drop_sources:
        return
    day = _day_of(el.get("startDate"))
    if day is None:
        return
    raw_type = el.get("workoutActivityType") or ""
    if raw_type.startswith(_WORKOUT_PREFIX):
        type_name = raw_type[len(_WORKOUT_PREFIX):]
    else:
        type_name = raw_type or "Unknown"
    duration_min = _to_float(el.get("duration"))
    duration_unit = el.get("durationUnit")
    if duration_min is not None and duration_unit == "h":
        duration_min *= 60.0
    elif duration_min is not None and duration_unit == "s":
        duration_min /= 60.0

    distance_raw = _to_float(el.get("totalDistance"))
    distance_unit = el.get("totalDistanceUnit")
    distance_km = _normalise(distance_raw, distance_unit, _UNIT_TO_KM) if distance_raw is not None else None

    energy_raw = _to_float(el.get("totalEnergyBurned"))
    energy_unit = el.get("totalEnergyBurnedUnit")
    energy_kcal = _normalise(energy_raw, energy_unit, _UNIT_TO_KCAL) if energy_raw is not None else None

    workout_row: dict = {"type": type_name, "start": el.get("startDate", "")}
    if duration_min is not None:
        workout_row["duration_min"] = round(duration_min, 1)
    if distance_km is not None:
        workout_row["distance_km"] = round(distance_km, 2)
    if energy_kcal is not None:
        workout_row["energy_kcal"] = round(energy_kcal, 0)

    agg = by_day.get(day)
    if agg is None:
        agg = HealthKitDailyAggregate(day=day)
        by_day[day] = agg
    agg.workouts.append(workout_row)
    if source:
        agg.sources.add(source)


def _normalised_for_field(field_name: str, value: float, unit: str | None) -> float | None:
    """Pick the unit-conversion table by destination field, return canonical value."""
    if field_name in ("weight_kg", "lean_body_mass_kg"):
        return _normalise(value, unit, _UNIT_TO_KG)
    if field_name == "distance_km":
        return _normalise(value, unit, _UNIT_TO_KM)
    if field_name == "height_cm":
        return _normalise(value, unit, _UNIT_TO_CM)
    if field_name in ("active_energy_kcal", "basal_energy_kcal"):
        return _normalise(value, unit, _UNIT_TO_KCAL)
    if field_name == "body_fat_pct":
        # Apple emits BodyFatPercentage as a fraction (0.196) with unit="%".
        # We want 19.6 in the rendered frontmatter.
        return value * 100.0
    # bmi, resting_hr, steps_total, flights_climbed — unitless; pass through.
    return value


def _maybe_int(field_name: str, value: float) -> int | float:
    """Fields that semantically count whole units render cleaner as ints."""
    if field_name in ("steps_total", "flights_climbed", "resting_hr"):
        return int(round(value))
    return value
