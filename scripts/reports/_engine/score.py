"""High-level scoring helper: load instrument + score answers + band.

The wedge uses this for offline / deterministic scoring (T04 testing
+ S02's first-PHQ-9-inference end-to-end). S02+ will compose this on
top of `lib/inference.py`'s structured output: agent returns
`{item_id: answer}`, this module turns it into a banded ScoreResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.reports._engine.instrument import Instrument, InstrumentMeta, load_instrument
from scripts.reports._engine.lib.likert import ScoreResult, score_answers


# Default coverage threshold for emitting a band. Mirrors M019
# bandable_coverage_pct from instrument.yaml's `inference` section.
# Instrument-level override accepted via `score_instrument()` kwarg.
DEFAULT_BANDABLE_COVERAGE_PCT = 80.0


@dataclass(frozen=True)
class ScoredInstrument:
    """Outcome of scoring one set of answers against one instrument."""

    meta: InstrumentMeta
    score: ScoreResult
    band: str | None  # None when coverage_pct < bandable_threshold
    bandable_threshold: float

    @property
    def bandable(self) -> bool:
        return self.band is not None

    @property
    def total(self) -> int:
        return self.score.total

    @property
    def coverage_pct(self) -> float:
        return self.score.coverage_pct


def score_instrument(
    instrument_dir: Path,
    answers: dict[str, int | None],
    bandable_threshold: float | None = None,
) -> ScoredInstrument:
    """Load an instrument from `instrument_dir` and score `answers`.

    Args:
        instrument_dir: versioned instrument directory (e.g.
            `scripts/reports/_engine/instruments/phq-9/v1.0.0/`).
        answers: `{item_id: value_or_None}`. Items not in the dict are
            treated as unanswered (lower coverage_pct).
        bandable_threshold: coverage_pct (0..100) at or above which a
            band is emitted. Below threshold, `band` is None — the
            score is "partial, not yet bandable". Defaults to
            DEFAULT_BANDABLE_COVERAGE_PCT (80.0).

    Returns:
        ScoredInstrument with `meta`, `score`, `band`, `bandable_threshold`.

    Raises:
        FileNotFoundError / ValueError: from load_instrument.
        ValueError: from score_answers (invalid value, unknown item id).
    """
    threshold = (
        bandable_threshold
        if bandable_threshold is not None
        else DEFAULT_BANDABLE_COVERAGE_PCT
    )
    instr: Instrument = load_instrument(instrument_dir)
    result = score_answers(list(instr.items), answers)
    band: str | None
    if result.coverage_pct >= threshold:
        band = instr.cutoffs.band_for(result.total)
    else:
        band = None
    return ScoredInstrument(
        meta=instr.meta,
        score=result,
        band=band,
        bandable_threshold=threshold,
    )
