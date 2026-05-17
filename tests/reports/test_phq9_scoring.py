"""End-to-end scoring test for PHQ-9 v1.0.0.

Covers each band with hand-filled answer arrays. Verifies the
instrument loads cleanly, scores sum correctly, and band-lookup
returns the expected DSM-IV labels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reports._engine.score import (
    DEFAULT_BANDABLE_COVERAGE_PCT,
    score_instrument,
)


PHQ9_DIR = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "reports" / "_engine" / "instruments" / "phq-9" / "v1.0.0"
)


def _all_answers(value: int) -> dict[str, int]:
    return {str(i): value for i in range(1, 10)}


class TestPHQ9Scoring:
    def test_phq9_loads(self) -> None:
        result = score_instrument(PHQ9_DIR, _all_answers(0))
        assert result.meta.slug == "phq-9"
        assert result.meta.version == "1.0.0"
        assert result.meta.likert.lo == 0
        assert result.meta.likert.hi == 3
        assert result.meta.scoring == "standard-sum"
        assert result.score.total_items == 9

    @pytest.mark.parametrize(
        "uniform_answer,expected_total,expected_band",
        [
            (0, 0, "minimal"),       # 9*0 = 0
            (1, 9, "mild"),          # 9*1 = 9 (top of mild)
            (2, 18, "moderately-severe"),  # 9*2 = 18
            (3, 27, "severe"),       # 9*3 = 27 (top of severe)
        ],
    )
    def test_uniform_answers_band(
        self, uniform_answer: int, expected_total: int, expected_band: str
    ) -> None:
        result = score_instrument(PHQ9_DIR, _all_answers(uniform_answer))
        assert result.score.total == expected_total
        assert result.band == expected_band
        assert result.bandable is True
        assert result.coverage_pct == 100.0

    def test_moderate_band_boundary(self) -> None:
        # Score 10 = bottom of moderate band.
        # Build answers summing to exactly 10: six 1s + two 2s + one 0.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 2, "8": 2, "9": 0}
        result = score_instrument(PHQ9_DIR, answers)
        assert result.score.total == 10
        assert result.band == "moderate"

    def test_minimal_top_boundary(self) -> None:
        # Score 4 = top of minimal. Four 1s + five 0s.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0}
        result = score_instrument(PHQ9_DIR, answers)
        assert result.score.total == 4
        assert result.band == "minimal"

    def test_mild_bottom_boundary(self) -> None:
        # Score 5 = bottom of mild.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 0, "7": 0, "8": 0, "9": 0}
        result = score_instrument(PHQ9_DIR, answers)
        assert result.score.total == 5
        assert result.band == "mild"

    def test_partial_answers_not_bandable_below_threshold(self) -> None:
        # 7/9 answered = 77.8% coverage, below default 80% threshold.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 1}
        result = score_instrument(PHQ9_DIR, answers)
        assert result.score.answered == 7
        assert result.bandable is False
        assert result.band is None
        assert result.coverage_pct < DEFAULT_BANDABLE_COVERAGE_PCT

    def test_partial_answers_bandable_at_threshold(self) -> None:
        # 8/9 answered = 88.9% coverage, above default 80% threshold.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 1, "8": 1}
        result = score_instrument(PHQ9_DIR, answers)
        assert result.score.answered == 8
        assert result.bandable is True
        assert result.band == "mild"  # score 8 = mild

    def test_custom_bandable_threshold(self) -> None:
        # Override threshold to 50% so 5/9 answered triggers band.
        answers = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1}
        result = score_instrument(PHQ9_DIR, answers, bandable_threshold=50.0)
        assert result.bandable is True
        assert result.band == "mild"  # total = 5

    def test_zero_answers_not_bandable(self) -> None:
        result = score_instrument(PHQ9_DIR, {})
        assert result.score.answered == 0
        assert result.bandable is False
        assert result.band is None
        assert result.coverage_pct == 0.0

    def test_substrate_inferable_curation_complete(self) -> None:
        """Every PHQ-9 item must have substrate_inferable explicitly
        curated. Loader ignores the field today but it's locked for
        S02's inference scope-resolver."""
        import yaml as yaml_mod
        items_path = PHQ9_DIR / "items.yaml"
        raw = yaml_mod.safe_load(items_path.read_text(encoding="utf-8"))
        for item in raw:
            assert "substrate_inferable" in item, (
                f"PHQ-9 item {item.get('id')!r} missing substrate_inferable curation"
            )
            assert isinstance(item["substrate_inferable"], bool), (
                f"PHQ-9 item {item.get('id')!r} substrate_inferable must be bool"
            )

    def test_q9_suicidal_ideation_never_inferable(self) -> None:
        """Q9 is suicidal-ideation — by hard rule, MUST be substrate_inferable=false.

        Auto-inferring this item is a methodological + ethical line.
        The curiosity-bridge asks; the inference-agent never guesses.
        Pin this in test so a future yaml edit can't silently flip it.
        """
        import yaml as yaml_mod
        raw = yaml_mod.safe_load((PHQ9_DIR / "items.yaml").read_text(encoding="utf-8"))
        q9 = next(item for item in raw if str(item["id"]) == "9")
        assert q9["substrate_inferable"] is False, (
            "PHQ-9 Q9 (suicidal ideation) MUST stay substrate_inferable=false. "
            "This is a non-negotiable methodological + ethical guard."
        )
