"""Tests for `scripts/reports/_engine/instrument.py` (yaml loader + validator)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reports._engine.instrument import (
    DEFAULT_LOOKBACK_DAYS,
    InferenceConfig,
    load_instrument,
)


_INSTRUMENTS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "reports" / "_engine" / "instruments"
)


def _live(slug: str):
    return load_instrument(_INSTRUMENTS_ROOT / slug / "v1.0.0")


GOOD_INSTRUMENT_YAML = """\
slug: test-instrument
version: 1.0.0
title: "Test instrument"
domain: test
licence: public-domain
licence-source: "synthetic, for tests"
likert: 0-3
scoring: standard-sum
"""

GOOD_ITEMS_YAML = """\
- {id: q1, text: "first item"}
- {id: q2, text: "second item"}
- {id: q3, text: "third item", reverse_coded: true}
"""

GOOD_CUTOFFS_YAML = """\
- {min: 0, max: 3, band: "low"}
- {min: 4, max: 6, band: "med"}
- {min: 7, max: 9, band: "high"}
"""


def _write_instrument(tmp_path: Path, instr: str, items: str, cutoffs: str) -> Path:
    d = tmp_path / "test-instrument" / "v1.0.0"
    d.mkdir(parents=True)
    (d / "instrument.yaml").write_text(instr, encoding="utf-8")
    (d / "items.yaml").write_text(items, encoding="utf-8")
    (d / "cutoffs.yaml").write_text(cutoffs, encoding="utf-8")
    return d


class TestLoadInstrument:
    def test_good_instrument_loads(self, tmp_path: Path) -> None:
        d = _write_instrument(tmp_path, GOOD_INSTRUMENT_YAML, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML)
        instr = load_instrument(d)
        assert instr.meta.slug == "test-instrument"
        assert instr.meta.version == "1.0.0"
        assert instr.meta.likert.lo == 0
        assert instr.meta.likert.hi == 3
        assert instr.meta.scoring == "standard-sum"
        assert instr.total_items == 3
        assert instr.items[2].reverse_coded is True
        assert instr.cutoffs.band_for(2) == "low"
        assert instr.cutoffs.band_for(5) == "med"
        assert instr.cutoffs.band_for(8) == "high"

    def test_missing_instrument_file_raises(self, tmp_path: Path) -> None:
        d = tmp_path / "incomplete"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            load_instrument(d)

    def test_unknown_scoring_strategy_rejected(self, tmp_path: Path) -> None:
        bad = GOOD_INSTRUMENT_YAML.replace("scoring: standard-sum", "scoring: bayesian-magic")
        d = _write_instrument(tmp_path, bad, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML)
        with pytest.raises(ValueError, match="not supported"):
            load_instrument(d)

    def test_missing_required_meta_key_rejected(self, tmp_path: Path) -> None:
        # Drop the `domain` field
        bad = "\n".join(
            line for line in GOOD_INSTRUMENT_YAML.splitlines() if not line.startswith("domain:")
        ) + "\n"
        d = _write_instrument(tmp_path, bad, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML)
        with pytest.raises(ValueError, match="missing required keys"):
            load_instrument(d)

    def test_duplicate_item_id_rejected(self, tmp_path: Path) -> None:
        bad_items = """\
- {id: q1, text: "first"}
- {id: q1, text: "duplicate id"}
- {id: q3, text: "third"}
"""
        d = _write_instrument(tmp_path, GOOD_INSTRUMENT_YAML, bad_items, GOOD_CUTOFFS_YAML)
        with pytest.raises(ValueError, match="duplicate item id"):
            load_instrument(d)

    def test_cutoff_range_mismatch_rejected(self, tmp_path: Path) -> None:
        # 3 items × scale 0-3 = achievable range 0..9.
        # Declare 0..6 only → mismatch must raise.
        bad_cutoffs = """\
- {min: 0, max: 3, band: "low"}
- {min: 4, max: 6, band: "med"}
"""
        d = _write_instrument(tmp_path, GOOD_INSTRUMENT_YAML, GOOD_ITEMS_YAML, bad_cutoffs)
        with pytest.raises(ValueError, match="does not match achievable"):
            load_instrument(d)

    def test_invalid_likert_scale_rejected(self, tmp_path: Path) -> None:
        bad = GOOD_INSTRUMENT_YAML.replace("likert: 0-3", "likert: 5-2")
        d = _write_instrument(tmp_path, bad, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML)
        with pytest.raises(ValueError):
            load_instrument(d)


class TestInferenceConfigSurfaced:
    """The loader surfaces the `inference:` section so downstream never
    re-parses the raw yaml for a single field."""

    def test_defaults_when_no_inference_section(self, tmp_path: Path) -> None:
        # GOOD_INSTRUMENT_YAML has no `inference:` block.
        d = _write_instrument(
            tmp_path, GOOD_INSTRUMENT_YAML, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML
        )
        cfg = load_instrument(d).meta.inference
        assert cfg == InferenceConfig()
        assert cfg.default_lookback_days == DEFAULT_LOOKBACK_DAYS
        assert cfg.model is None

    def test_inference_section_parsed(self) -> None:
        cfg = _live("phq-9").meta.inference
        assert cfg.enabled is True
        assert cfg.min_confidence == 0.75
        assert cfg.bandable_coverage_pct == 80.0
        assert cfg.default_lookback_days == 14
        assert cfg.max_curiosity_per_run == 3
        assert cfg.model is None

    def test_per_instrument_model_override_surfaced(self) -> None:
        # ISI declares `inference.model: claude-sonnet-4-6`.
        assert _live("isi").meta.inference.model == "claude-sonnet-4-6"

    def test_lookback_varies_by_instrument(self) -> None:
        assert _live("k6").meta.inference.default_lookback_days == 30
        assert _live("asrs-v1.1").meta.inference.default_lookback_days == 180

    def test_non_mapping_inference_rejected(self, tmp_path: Path) -> None:
        bad = GOOD_INSTRUMENT_YAML + "inference: not-a-mapping\n"
        d = _write_instrument(tmp_path, bad, GOOD_ITEMS_YAML, GOOD_CUTOFFS_YAML)
        with pytest.raises(ValueError, match="inference"):
            load_instrument(d)


class TestMaxTotalAndConcern:
    def test_max_total_is_scale_hi_times_items(self) -> None:
        assert _live("phq-9").max_total == 27   # 9 items × 0-3
        assert _live("gad-7").max_total == 21   # 7 items × 0-3
        assert _live("who-5").max_total == 25   # 5 items × 0-5
        assert _live("olbi").max_total == 80    # 16 items × 1-5

    def test_phq9_concern_bands(self) -> None:
        assert _live("phq-9").concern_bands == (
            "moderate", "moderately-severe", "severe",
        )

    def test_previously_unflaggable_live_instruments_now_declare_concern(self) -> None:
        """isi / olbi / pss-10 were structurally flag-blind (absent from the
        old hardcoded severe_bands table). Each must now declare concern
        bands so the meta-report can raise a flag."""
        assert _live("isi").concern_bands == ("moderate", "severe")
        assert _live("olbi").concern_bands == ("high", "very-high")
        assert _live("pss-10").concern_bands == ("high",)

    def test_every_live_instrument_declares_at_least_one_concern_band(self) -> None:
        for slug_dir in sorted(_INSTRUMENTS_ROOT.iterdir()):
            if not slug_dir.is_dir():
                continue
            instr = load_instrument(slug_dir / "v1.0.0")
            assert instr.concern_bands, (
                f"{instr.meta.slug} declares no concern band — it can never "
                f"raise a meta-report flag"
            )
