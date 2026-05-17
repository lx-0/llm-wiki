"""Tests for `scripts/reports/_engine/instrument.py` (yaml loader + validator)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reports._engine.instrument import load_instrument


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
