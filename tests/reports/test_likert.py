"""Tests for `scripts/reports/_engine/lib/likert.py`."""

from __future__ import annotations

import pytest

from scripts.reports._engine.lib.likert import (
    LikertItem,
    LikertScale,
    score_answers,
)


class TestLikertScale:
    def test_parse_valid_scales(self) -> None:
        assert LikertScale.parse("0-3") == LikertScale(0, 3)
        assert LikertScale.parse("1-5") == LikertScale(1, 5)
        assert LikertScale.parse("1-7") == LikertScale(1, 7)

    @pytest.mark.parametrize("bad", ["", "0", "3-3", "5-1", "abc", "0--3"])
    def test_parse_invalid_scales(self, bad: str) -> None:
        with pytest.raises(ValueError):
            LikertScale.parse(bad)

    def test_validate_in_range(self) -> None:
        s = LikertScale(0, 3)
        s.validate(0)
        s.validate(2)
        s.validate(3)

    @pytest.mark.parametrize("bad", [-1, 4, 10])
    def test_validate_out_of_range(self, bad: int) -> None:
        with pytest.raises(ValueError):
            LikertScale(0, 3).validate(bad)

    def test_validate_rejects_non_int(self) -> None:
        with pytest.raises(ValueError):
            LikertScale(0, 3).validate(1.5)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            LikertScale(0, 3).validate(True)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            LikertScale(0, 3).validate("2")  # type: ignore[arg-type]

    def test_reverse_symmetric(self) -> None:
        s = LikertScale(0, 3)
        assert s.reverse(0) == 3
        assert s.reverse(1) == 2
        assert s.reverse(2) == 1
        assert s.reverse(3) == 0
        # 1-5 scale: midpoint maps to itself
        s5 = LikertScale(1, 5)
        assert s5.reverse(3) == 3
        assert s5.reverse(1) == 5


class TestScoreAnswers:
    @pytest.fixture
    def phq9_items(self) -> list[LikertItem]:
        scale = LikertScale(0, 3)
        return [LikertItem(id=f"q{i}", scale=scale) for i in range(1, 10)]

    def test_full_answers_sum_correctly(self, phq9_items: list[LikertItem]) -> None:
        answers = {f"q{i}": 2 for i in range(1, 10)}
        result = score_answers(phq9_items, answers)
        assert result.total == 18
        assert result.answered == 9
        assert result.total_items == 9
        assert result.coverage_pct == 100.0

    def test_zero_score_all_zeros(self, phq9_items: list[LikertItem]) -> None:
        answers = {f"q{i}": 0 for i in range(1, 10)}
        result = score_answers(phq9_items, answers)
        assert result.total == 0
        assert result.answered == 9

    def test_partial_answers_coverage(self, phq9_items: list[LikertItem]) -> None:
        answers = {"q1": 3, "q2": 2, "q3": None}
        # q4..q9 absent entirely — also treated as unanswered
        result = score_answers(phq9_items, answers)
        assert result.total == 5
        assert result.answered == 2
        assert result.coverage_pct == pytest.approx(22.2, abs=0.05)

    def test_reverse_coding_flips_value(self) -> None:
        scale = LikertScale(0, 3)
        items = [
            LikertItem(id="forward", scale=scale, reverse_coded=False),
            LikertItem(id="reversed", scale=scale, reverse_coded=True),
        ]
        # forward answer 1, reversed answer 1 → reversed normalised to 2
        result = score_answers(items, {"forward": 1, "reversed": 1})
        assert result.total == 1 + 2
        assert result.per_item_normalised == {"forward": 1, "reversed": 2}

    def test_subscale_aggregation(self) -> None:
        scale = LikertScale(0, 3)
        items = [
            LikertItem(id="a1", scale=scale, subscale="A"),
            LikertItem(id="a2", scale=scale, subscale="A"),
            LikertItem(id="b1", scale=scale, subscale="B"),
            LikertItem(id="ungrouped", scale=scale),
        ]
        result = score_answers(items, {"a1": 2, "a2": 3, "b1": 1, "ungrouped": 1})
        assert result.total == 7
        assert result.per_subscale == {"A": 5, "B": 1}

    def test_out_of_range_answer_raises(self, phq9_items: list[LikertItem]) -> None:
        with pytest.raises(ValueError):
            score_answers(phq9_items, {"q1": 5})

    def test_unknown_item_id_raises(self, phq9_items: list[LikertItem]) -> None:
        with pytest.raises(ValueError):
            score_answers(phq9_items, {"q99": 1})

    def test_empty_answers_zero_coverage(self, phq9_items: list[LikertItem]) -> None:
        result = score_answers(phq9_items, {})
        assert result.total == 0
        assert result.answered == 0
        assert result.coverage_pct == 0.0

    def test_no_items_no_division_error(self) -> None:
        result = score_answers([], {})
        assert result.total == 0
        assert result.coverage_pct == 0.0
