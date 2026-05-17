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
    meta = InstrumentMeta(
        slug=str(meta_raw["slug"]),
        version=str(meta_raw["version"]),
        title=str(meta_raw["title"]),
        domain=str(meta_raw["domain"]),
        likert=scale,
        scoring=str(meta_raw["scoring"]),
        licence=str(meta_raw["licence"]),
        licence_source=str(meta_raw["licence-source"]),
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
