"""Tests for `scripts/reports/_engine/lib/cutoffs.py`."""

from __future__ import annotations

import pytest

from scripts.reports._engine.lib.cutoffs import Band, Cutoffs


PHQ9_BANDS = [
    {"min": 0, "max": 4, "band": "minimal"},
    {"min": 5, "max": 9, "band": "mild"},
    {"min": 10, "max": 14, "band": "moderate"},
    {"min": 15, "max": 19, "band": "moderately-severe"},
    {"min": 20, "max": 27, "band": "severe"},
]


class TestCutoffs:
    def test_load_phq9_bands(self) -> None:
        c = Cutoffs.from_list(PHQ9_BANDS)
        assert len(c.bands) == 5
        assert c.range == (0, 27)

    def test_band_lookup_within_each_band(self) -> None:
        c = Cutoffs.from_list(PHQ9_BANDS)
        assert c.band_for(0) == "minimal"
        assert c.band_for(4) == "minimal"
        assert c.band_for(5) == "mild"
        assert c.band_for(9) == "mild"
        assert c.band_for(10) == "moderate"
        assert c.band_for(14) == "moderate"
        assert c.band_for(15) == "moderately-severe"
        assert c.band_for(19) == "moderately-severe"
        assert c.band_for(20) == "severe"
        assert c.band_for(27) == "severe"

    def test_boundary_scores_no_off_by_one(self) -> None:
        # Boundary discipline: max of one band + 1 = min of next.
        c = Cutoffs.from_list(PHQ9_BANDS)
        # Score 4 = top of minimal, score 5 = bottom of mild
        assert c.band_for(4) == "minimal"
        assert c.band_for(5) == "mild"

    @pytest.mark.parametrize("bad_score", [-1, 28, 100])
    def test_out_of_range_raises(self, bad_score: int) -> None:
        c = Cutoffs.from_list(PHQ9_BANDS)
        with pytest.raises(ValueError):
            c.band_for(bad_score)

    def test_empty_bands_rejected(self) -> None:
        with pytest.raises(ValueError):
            Cutoffs.from_list([])

    def test_band_max_less_than_min_rejected(self) -> None:
        bad = [{"min": 5, "max": 3, "band": "broken"}]
        with pytest.raises(ValueError):
            Cutoffs.from_list(bad)

    def test_unsorted_bands_rejected(self) -> None:
        unsorted = [
            {"min": 5, "max": 9, "band": "mild"},
            {"min": 0, "max": 4, "band": "minimal"},
        ]
        with pytest.raises(ValueError):
            Cutoffs.from_list(unsorted)

    def test_gap_between_bands_rejected(self) -> None:
        # Gap between max=4 and min=6 (missing 5).
        gapped = [
            {"min": 0, "max": 4, "band": "low"},
            {"min": 6, "max": 10, "band": "high"},
        ]
        with pytest.raises(ValueError):
            Cutoffs.from_list(gapped)

    def test_overlap_between_bands_rejected(self) -> None:
        overlap = [
            {"min": 0, "max": 5, "band": "low"},
            {"min": 5, "max": 10, "band": "high"},
        ]
        with pytest.raises(ValueError):
            Cutoffs.from_list(overlap)

    def test_single_band_full_range(self) -> None:
        c = Cutoffs.from_list([{"min": 0, "max": 5, "band": "any"}])
        assert c.band_for(3) == "any"
        assert c.range == (0, 5)


class TestBand:
    def test_contains_inclusive(self) -> None:
        b = Band(min=5, max=9, band="mild")
        assert b.contains(5)
        assert b.contains(7)
        assert b.contains(9)
        assert not b.contains(4)
        assert not b.contains(10)

    def test_concern_defaults_false(self) -> None:
        assert Band(min=0, max=4, band="minimal").concern is False


class TestConcernBands:
    def test_concern_flag_parsed_from_list(self) -> None:
        c = Cutoffs.from_list([
            {"min": 0, "max": 4, "band": "minimal"},
            {"min": 5, "max": 9, "band": "mild"},
            {"min": 10, "max": 14, "band": "moderate", "concern": True},
            {"min": 15, "max": 21, "band": "severe", "concern": True},
        ])
        assert c.concern_bands == ("moderate", "severe")

    def test_no_concern_flags_yields_empty_tuple(self) -> None:
        c = Cutoffs.from_list(PHQ9_BANDS)  # no concern keys in this fixture
        assert c.concern_bands == ()

    def test_concern_absent_key_is_false(self) -> None:
        c = Cutoffs.from_list([
            {"min": 0, "max": 5, "band": "low"},
            {"min": 6, "max": 10, "band": "high", "concern": True},
        ])
        assert c.bands[0].concern is False
        assert c.bands[1].concern is True
        assert c.concern_bands == ("high",)
