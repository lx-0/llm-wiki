"""Scale-agnostic Likert scoring with reverse-coding + subscale aggregation.

A psychometric instrument-yaml declares its items (list of {id, text,
scale, optional reverse_coded, optional subscale}), and the engine
computes:

  - per-item normalised value (always positive; reverse-coding flipped)
  - per-subscale sum
  - total sum across all answered items
  - coverage stats (answered / total / coverage_pct)

Scale support: 0-3 (PHQ-9, GAD-7), 1-5 (most personality), 1-7 (some
Likert-7 scales). The scale-range is declared at the instrument level
in `instrument.yaml` as `likert: "0-3"` etc; this module parses that
string and validates answers fall inside.

Reverse-coding: an item with `reverse_coded: true` and answer `a` on
scale `(lo, hi)` is normalised to `hi + lo - a` (the symmetric flip).
This is the standard psychometric convention.

Unanswered items: passed as `None` in the answers dict (or absent).
They contribute nothing to sums and lower the coverage_pct.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LikertScale:
    """Inclusive integer scale (`lo`..`hi`). Parsed from `"lo-hi"`."""

    lo: int
    hi: int

    @classmethod
    def parse(cls, spec: str) -> "LikertScale":
        if not isinstance(spec, str) or "-" not in spec:
            raise ValueError(
                f"Likert scale spec must be 'lo-hi' (got {spec!r})"
            )
        try:
            lo_s, hi_s = spec.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        except ValueError as exc:
            raise ValueError(f"Likert scale spec invalid: {spec!r}") from exc
        if hi <= lo:
            raise ValueError(
                f"Likert scale must have hi > lo (got lo={lo} hi={hi})"
            )
        return cls(lo=lo, hi=hi)

    def validate(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"Likert answer must be int, got {type(value).__name__}: {value!r}"
            )
        if not (self.lo <= value <= self.hi):
            raise ValueError(
                f"Likert answer {value} outside scale {self.lo}..{self.hi}"
            )

    def reverse(self, value: int) -> int:
        """Symmetric flip: maps `lo` to `hi`, `hi` to `lo`, midpoints to midpoints."""
        return self.hi + self.lo - value


@dataclass(frozen=True)
class LikertItem:
    """One scoring-relevant item declared in items.yaml."""

    id: str
    scale: LikertScale
    reverse_coded: bool = False
    subscale: str | None = None  # None = belongs to the overall total only


@dataclass(frozen=True)
class ScoreResult:
    """Outcome of scoring a complete answer-set against an item-list."""

    total: int
    per_subscale: dict[str, int]
    per_item_normalised: dict[str, int]  # answered items only
    answered: int
    total_items: int

    @property
    def coverage_pct(self) -> float:
        if self.total_items == 0:
            return 0.0
        return round(100.0 * self.answered / self.total_items, 1)


def score_answers(
    items: list[LikertItem],
    answers: dict[str, int | None],
) -> ScoreResult:
    """Aggregate answers into total + per-subscale sums + coverage stats.

    Args:
        items: ordered item declarations from items.yaml.
        answers: `{item_id: value | None}`. Unanswered items can be
            present-with-None or absent — both treated as unanswered.

    Raises:
        ValueError: if an answer falls outside its item's scale, or
            if `answers` contains an item_id not in `items`.
    """
    known_ids = {it.id for it in items}
    unknown_ids = set(answers) - known_ids
    if unknown_ids:
        raise ValueError(
            f"answers contain unknown item ids: {sorted(unknown_ids)}"
        )

    total = 0
    per_subscale: dict[str, int] = {}
    per_item_norm: dict[str, int] = {}
    answered = 0

    for item in items:
        raw = answers.get(item.id)
        if raw is None:
            continue
        item.scale.validate(raw)
        normalised = item.scale.reverse(raw) if item.reverse_coded else raw
        per_item_norm[item.id] = normalised
        total += normalised
        if item.subscale is not None:
            per_subscale[item.subscale] = per_subscale.get(item.subscale, 0) + normalised
        answered += 1

    return ScoreResult(
        total=total,
        per_subscale=per_subscale,
        per_item_normalised=per_item_norm,
        answered=answered,
        total_items=len(items),
    )
