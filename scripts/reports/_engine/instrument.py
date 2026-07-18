"""Instrument-yaml schema + loader + validator.

An instrument lives at:

    scripts/reports/_engine/instruments/<slug>/<version>/
        instrument.yaml   # meta (id, title, scale, scoring strategy, licence)
        items.yaml        # ordered list of items + reverse-flags + subscale-ids
        cutoffs.yaml      # banding ladder
        (optional)
        scoring.py        # for non-sum strategies (post-wedge)

This module loads and validates that file-set into typed objects.
The wedge uses `scoring: "standard-sum"` only — `scoring.py` is a
post-wedge extension point.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from scripts.reports._engine.lib.cutoffs import Cutoffs
from scripts.reports._engine.lib.likert import LikertItem, LikertScale


SUPPORTED_SCORING = ("standard-sum",)

# Default lookback if instrument.yaml's `inference` section omits it.
DEFAULT_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class InferenceConfig:
    """The `inference:` section of instrument.yaml — the defaults the
    runner + audit probe consume for scope resolution + scoring.

    Surfaced by `load_instrument` so downstream never re-parses the raw
    yaml to recover a single field (the pre-deepening runner + audit
    probe each re-read `default_lookback_days` / `model` by hand). Unknown
    keys are ignored; missing keys fall back to these defaults so a
    pre-inference instrument.yaml still loads.
    """

    enabled: bool = True
    min_confidence: float = 0.75
    bandable_coverage_pct: float = 80.0
    default_lookback_days: int = DEFAULT_LOOKBACK_DAYS
    max_curiosity_per_run: int = 3
    model: str | None = None  # per-instrument model override; None = engine default

    @classmethod
    def from_raw(cls, raw: dict | None) -> "InferenceConfig":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            min_confidence=float(raw.get("min_confidence", 0.75)),
            bandable_coverage_pct=float(raw.get("bandable_coverage_pct", 80.0)),
            default_lookback_days=int(
                raw.get("default_lookback_days", DEFAULT_LOOKBACK_DAYS)
            ),
            max_curiosity_per_run=int(raw.get("max_curiosity_per_run", 3)),
            model=(str(raw["model"]) if raw.get("model") else None),
        )


@dataclass(frozen=True)
class InstrumentMeta:
    """Parsed `instrument.yaml` fields. Source of truth for headers."""

    slug: str
    version: str
    title: str
    domain: str
    likert: LikertScale
    scoring: str
    licence: str
    licence_source: str
    inference: InferenceConfig


@dataclass(frozen=True)
class Instrument:
    """A loaded instrument: meta + items + cutoffs."""

    meta: InstrumentMeta
    items: tuple[LikertItem, ...]
    cutoffs: Cutoffs
    instrument_path: Path  # directory the files were loaded from

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def max_total(self) -> int:
        """Highest achievable total: every item answered at the scale
        ceiling. Reverse-coding is score-preserving, so this holds for
        mixed reverse/forward items too."""
        return self.meta.likert.hi * len(self.items)

    @property
    def concern_bands(self) -> tuple[str, ...]:
        """Band labels this instrument flags as clinically elevated —
        read straight from cutoffs.yaml's `concern: true` entries."""
        return self.cutoffs.concern_bands


def _require_keys(d: dict, required: set[str], where: str) -> None:
    missing = required - set(d)
    if missing:
        raise ValueError(f"{where}: missing required keys: {sorted(missing)}")


def load_instrument(instrument_dir: Path) -> Instrument:
    """Load instrument.yaml + items.yaml + cutoffs.yaml from a versioned dir.

    Args:
        instrument_dir: path to e.g.
            `scripts/reports/_engine/instruments/phq-9/v1.0.0/`.

    Raises:
        FileNotFoundError: if any of the three yaml files is missing.
        ValueError: if any file's schema is invalid.
    """
    instrument_dir = Path(instrument_dir)
    instrument_yaml = instrument_dir / "instrument.yaml"
    items_yaml = instrument_dir / "items.yaml"
    cutoffs_yaml = instrument_dir / "cutoffs.yaml"

    for path in (instrument_yaml, items_yaml, cutoffs_yaml):
        if not path.is_file():
            raise FileNotFoundError(
                f"instrument file missing: {path} (relative to {instrument_dir})"
            )

    meta_raw = yaml.safe_load(instrument_yaml.read_text(encoding="utf-8"))
    if not isinstance(meta_raw, dict):
        raise ValueError(f"{instrument_yaml}: top-level must be a mapping")
    _require_keys(
        meta_raw,
        {"slug", "version", "title", "domain", "likert", "scoring", "licence", "licence-source"},
        f"{instrument_yaml}",
    )
    if meta_raw["scoring"] not in SUPPORTED_SCORING:
        raise ValueError(
            f"{instrument_yaml}: scoring={meta_raw['scoring']!r} not supported. "
            f"Supported: {SUPPORTED_SCORING}"
        )
    scale = LikertScale.parse(str(meta_raw["likert"]))
    inference_raw = meta_raw.get("inference")
    if inference_raw is not None and not isinstance(inference_raw, dict):
        raise ValueError(f"{instrument_yaml}: `inference` must be a mapping")
    meta = InstrumentMeta(
        slug=str(meta_raw["slug"]),
        version=str(meta_raw["version"]),
        title=str(meta_raw["title"]),
        domain=str(meta_raw["domain"]),
        likert=scale,
        scoring=str(meta_raw["scoring"]),
        licence=str(meta_raw["licence"]),
        licence_source=str(meta_raw["licence-source"]),
        inference=InferenceConfig.from_raw(inference_raw),
    )

    items_raw = yaml.safe_load(items_yaml.read_text(encoding="utf-8"))
    if not isinstance(items_raw, list) or not items_raw:
        raise ValueError(f"{items_yaml}: must be a non-empty list of items")
    items: list[LikertItem] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"{items_yaml}[{idx}]: must be a mapping")
        _require_keys(raw, {"id", "text"}, f"{items_yaml}[{idx}]")
        item_id = str(raw["id"])
        if item_id in seen_ids:
            raise ValueError(f"{items_yaml}: duplicate item id {item_id!r}")
        seen_ids.add(item_id)
        items.append(
            LikertItem(
                id=item_id,
                scale=scale,
                reverse_coded=bool(raw.get("reverse_coded", False)),
                subscale=(str(raw["subscale"]) if raw.get("subscale") else None),
            )
        )

    cutoffs_raw = yaml.safe_load(cutoffs_yaml.read_text(encoding="utf-8"))
    if not isinstance(cutoffs_raw, list):
        raise ValueError(f"{cutoffs_yaml}: must be a list of band entries")
    cutoffs = Cutoffs.from_list(cutoffs_raw)

    # Sanity: cutoffs.range must cover the achievable score range
    # (n_items * scale.lo) to (n_items * scale.hi). Catches off-by-one
    # in cutoffs.yaml that would silently mis-band edge scores.
    achievable_min = len(items) * scale.lo
    achievable_max = len(items) * scale.hi
    cutoff_lo, cutoff_hi = cutoffs.range
    if (cutoff_lo, cutoff_hi) != (achievable_min, achievable_max):
        raise ValueError(
            f"{cutoffs_yaml}: declared range {cutoff_lo}..{cutoff_hi} does "
            f"not match achievable score range {achievable_min}..{achievable_max} "
            f"(n_items={len(items)}, scale={scale.lo}..{scale.hi})"
        )

    return Instrument(
        meta=meta,
        items=tuple(items),
        cutoffs=cutoffs,
        instrument_path=instrument_dir,
    )
