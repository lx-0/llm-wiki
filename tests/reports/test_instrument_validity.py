"""Cross-instrument validity test for the 5 wedge instruments.

Pins each instrument's load + score-against-synthetic-answers and
asserts the band-lookup at the published clinical cutoff. The
embedded-methodology contract requires items.yaml + cutoffs.yaml to
stay stable across versions; the next file-edit that breaks an
instrument's load surfaces here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reports._engine.instrument import load_instrument
from scripts.reports._engine.score import score_instrument


INSTRUMENTS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "reports" / "_engine" / "instruments"
)


WEDGE_INSTRUMENTS = [
    ("phq-9", "1.0.0", 9, 27),
    ("gad-7", "1.0.0", 7, 21),
    ("asrs-v1.1", "1.0.0", 18, 72),
    ("who-5", "1.0.0", 5, 25),
    ("k6", "1.0.0", 6, 24),
    ("pss-10", "1.0.0", 10, 40),
    ("isi", "1.0.0", 7, 28),
    ("olbi", "1.0.0", 16, 80),
]


@pytest.mark.parametrize("slug,version,n_items,max_total", WEDGE_INSTRUMENTS)
def test_wedge_instrument_loads(
    slug: str, version: str, n_items: int, max_total: int
) -> None:
    """Each wedge instrument loads + has the expected item count + total range.

    Achievable range = (n_items * likert.lo, n_items * likert.hi).
    For 0-scale instruments (PHQ-9 / GAD-7 / ASRS / WHO-5 / K6 /
    PSS-10 / ISI) this is (0, max_total). For 1-scale instruments
    (OLBI) this is (n_items, max_total) because the lowest literal
    score is 1, not 0.
    """
    instr = load_instrument(INSTRUMENTS_ROOT / slug / f"v{version}")
    assert instr.meta.slug == slug
    assert instr.meta.version == version
    assert instr.total_items == n_items
    expected_max = n_items * instr.meta.likert.hi
    expected_min = n_items * instr.meta.likert.lo
    assert expected_max == max_total
    assert instr.cutoffs.range == (expected_min, expected_max)


def _direction_answer_set(slug: str, version: str, direction: str) -> dict:
    """Build the answer dict that yields min (direction='min') or max
    (direction='max') score for an instrument, accounting for reverse-
    coded items. For instruments WITHOUT reverse-coding this is the
    naive 'all lo' / 'all hi'; with reverse-coding items get the
    opposite literal value so post-reverse they contribute min/max.
    """
    import yaml as yaml_mod
    items_path = INSTRUMENTS_ROOT / slug / f"v{version}" / "items.yaml"
    instr_path = INSTRUMENTS_ROOT / slug / f"v{version}" / "instrument.yaml"
    raw_instr = yaml_mod.safe_load(instr_path.read_text(encoding="utf-8"))
    lo, hi = (int(x) for x in str(raw_instr["likert"]).split("-"))
    items = yaml_mod.safe_load(items_path.read_text(encoding="utf-8"))
    out = {}
    for item in items:
        is_rev = bool(item.get("reverse_coded", False))
        if direction == "min":
            out[str(item["id"])] = hi if is_rev else lo
        else:  # max
            out[str(item["id"])] = lo if is_rev else hi
    return out


@pytest.mark.parametrize("slug,version,n_items,max_total", WEDGE_INSTRUMENTS)
def test_wedge_min_direction_bottom_band(
    slug: str, version: str, n_items: int, max_total: int
) -> None:
    """min-direction answer set → score = 0 → bottom band.

    For instruments with reverse-coded items, 'min-direction' means
    `lo` for forward items + `hi` for reverse items (so post-reverse
    they contribute the literal `lo` value). Total = 0 for all wedge
    instruments by construction (cutoffs.range starts at 0)."""
    answers = _direction_answer_set(slug, version, "min")
    result = score_instrument(INSTRUMENTS_ROOT / slug / f"v{version}", answers)
    instr = load_instrument(INSTRUMENTS_ROOT / slug / f"v{version}")
    # Total = 0 for instruments whose cutoffs start at 0 (PHQ-9 / GAD-7 /
    # ASRS / WHO-5 / K6 / PSS-10 / ISI), or = cutoffs.range[0] for
    # OLBI (16 because 16 items × likert.lo=1).
    expected_min = instr.cutoffs.range[0]
    assert result.score.total == expected_min
    assert result.coverage_pct == 100.0
    assert result.band is not None


@pytest.mark.parametrize("slug,version,n_items,max_total", WEDGE_INSTRUMENTS)
def test_wedge_max_direction_top_band(
    slug: str, version: str, n_items: int, max_total: int
) -> None:
    """max-direction answer set → score = max_total → top band."""
    answers = _direction_answer_set(slug, version, "max")
    result = score_instrument(INSTRUMENTS_ROOT / slug / f"v{version}", answers)
    assert result.score.total == max_total
    assert result.band is not None


class TestPublishedCutoffs:
    """Pin the published clinical thresholds — these MUST stay stable.

    PHQ-9: 10+ = moderate or worse (Kroenke 2001).
    GAD-7: 10+ = moderate or worse (Spitzer 2006).
    WHO-5: ≤12 raw = depression-screen positive (WHO 1998, < 50%).
    K6: 13+ = serious psychological distress (Kessler 2003).
    """

    def test_phq9_threshold_10_moderate(self) -> None:
        # Build a score-10 answer set: 2+1+2+1+1+1+1+1+0 = 10
        answers = {"1": 2, "2": 1, "3": 2, "4": 1, "5": 1, "6": 1, "7": 1, "8": 1, "9": 0}
        result = score_instrument(INSTRUMENTS_ROOT / "phq-9" / "v1.0.0", answers)
        assert result.score.total == 10
        assert result.band == "moderate"

    def test_gad7_threshold_10_moderate(self) -> None:
        # Build a score-10 answer set: 4 × 2 + 2 × 1 + 1 × 0 = 10
        answers = {"1": 2, "2": 2, "3": 2, "4": 2, "5": 1, "6": 1, "7": 0}
        result = score_instrument(INSTRUMENTS_ROOT / "gad-7" / "v1.0.0", answers)
        assert result.score.total == 10
        assert result.band == "moderate"

    def test_who5_threshold_12_low(self) -> None:
        # Score 12 = raw ≤12 → "low" band (just under the < 50% line)
        answers = {"1": 3, "2": 3, "3": 3, "4": 2, "5": 1}
        result = score_instrument(INSTRUMENTS_ROOT / "who-5" / "v1.0.0", answers)
        assert result.score.total == 12
        assert result.band == "low"

    def test_who5_threshold_8_poor(self) -> None:
        # Score 7 = solidly poor (= 28% on the 0-100 scale)
        answers = {"1": 2, "2": 2, "3": 1, "4": 1, "5": 1}
        result = score_instrument(INSTRUMENTS_ROOT / "who-5" / "v1.0.0", answers)
        assert result.score.total == 7
        assert result.band == "poor"

    def test_k6_threshold_13_high(self) -> None:
        # Score 13 = clinical-cutoff "serious distress" per Kessler 2003
        answers = {"1": 3, "2": 2, "3": 2, "4": 2, "5": 2, "6": 2}
        result = score_instrument(INSTRUMENTS_ROOT / "k6" / "v1.0.0", answers)
        assert result.score.total == 13
        assert result.band == "high"

    def test_k6_threshold_12_moderate(self) -> None:
        # Score 12 = one below cutoff → still moderate band
        answers = {"1": 2, "2": 2, "3": 2, "4": 2, "5": 2, "6": 2}
        result = score_instrument(INSTRUMENTS_ROOT / "k6" / "v1.0.0", answers)
        assert result.score.total == 12
        assert result.band == "moderate"


class TestASRSSubscales:
    """ASRS-v1.1 splits 18 items into Part A (6) and Part B (12)."""

    def test_asrs_subscales_present(self) -> None:
        instr = load_instrument(INSTRUMENTS_ROOT / "asrs-v1.1" / "v1.0.0")
        subscales = {it.subscale for it in instr.items}
        assert subscales == {"Part-A", "Part-B"}

    def test_asrs_part_a_six_items(self) -> None:
        instr = load_instrument(INSTRUMENTS_ROOT / "asrs-v1.1" / "v1.0.0")
        part_a_items = [it for it in instr.items if it.subscale == "Part-A"]
        assert len(part_a_items) == 6

    def test_asrs_part_b_twelve_items(self) -> None:
        instr = load_instrument(INSTRUMENTS_ROOT / "asrs-v1.1" / "v1.0.0")
        part_b_items = [it for it in instr.items if it.subscale == "Part-B"]
        assert len(part_b_items) == 12

    def test_asrs_subscale_sums_correct(self) -> None:
        answers = {str(i): 2 for i in range(1, 19)}
        result = score_instrument(
            INSTRUMENTS_ROOT / "asrs-v1.1" / "v1.0.0", answers
        )
        # 6 items × 2 = 12 for Part A; 12 × 2 = 24 for Part B
        assert result.score.per_subscale == {"Part-A": 12, "Part-B": 24}
        assert result.score.total == 36


class TestSubstrateInferableCuration:
    """Every wedge item must have substrate_inferable explicitly curated.

    Loader silently ignores the flag today, but S02-T04's runner +
    inference prompt depend on it. Missing curation would silently
    let the agent guess sensitive items.
    """

    @pytest.mark.parametrize("slug,version,n_items,max_total", WEDGE_INSTRUMENTS)
    def test_all_items_have_substrate_inferable(
        self, slug: str, version: str, n_items: int, max_total: int
    ) -> None:
        import yaml as yaml_mod
        items_path = INSTRUMENTS_ROOT / slug / f"v{version}" / "items.yaml"
        raw = yaml_mod.safe_load(items_path.read_text(encoding="utf-8"))
        for item in raw:
            assert "substrate_inferable" in item, (
                f"{slug} v{version} item {item.get('id')!r}: "
                f"missing substrate_inferable curation"
            )
            assert isinstance(item["substrate_inferable"], bool), (
                f"{slug} v{version} item {item.get('id')!r}: "
                f"substrate_inferable must be bool, got {type(item['substrate_inferable'])}"
            )

    def test_inferable_coverage_per_instrument(self) -> None:
        """Document each wedge instrument's substrate-inferable coverage.

        These ratios are the methodologically-honest ceiling on coverage_pct
        from substrate-alone (before any curiosity-bridge input). Test
        pins them so any silent drift surfaces.
        """
        import yaml as yaml_mod
        expected_inferable = {
            "phq-9": 4,        # of 9 items = 44%
            "gad-7": 4,        # of 7 items = 57%
            "asrs-v1.1": 6,    # of 18 items = 33%
            "who-5": 4,        # of 5 items = 80% — highest single-screen
            "k6": 2,           # of 6 items = 33% — lowest (dropped from wedge)
            "pss-10": 5,       # of 10 items = 50%
            "isi": 4,          # of 7 items = 57% — Oura items 1-3, item 7 sessions
            "olbi": 8,         # of 16 items = 50% — 4 each per subscale
        }
        for slug, expected in expected_inferable.items():
            items_path = INSTRUMENTS_ROOT / slug / "v1.0.0" / "items.yaml"
            raw = yaml_mod.safe_load(items_path.read_text(encoding="utf-8"))
            actual = sum(1 for item in raw if item.get("substrate_inferable"))
            assert actual == expected, (
                f"{slug}: expected {expected} substrate_inferable items, got {actual}. "
                f"Silent drift — investigate before next wedge run."
            )
