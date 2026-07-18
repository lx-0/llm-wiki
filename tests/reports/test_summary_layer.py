"""Tests for the M019-S04 meta-report layer (timeline + charts + summary)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.reports._engine.lib.charts import (
    render_radar,
    render_sparkline,
    render_timeline,
)
from scripts.reports._engine.lib.render_summary import render_summary
from scripts.reports._engine.lib.timeline import (
    InstrumentSnapshot,
    RunSnapshot,
    Timeline,
    load_timeline,
    snapshot_from_dir,
)


def _make_report(
    path: Path,
    *,
    slug: str,
    version: str,
    timestamp: str,
    total: int,
    band: str | None,
    coverage_pct: float,
    answered: int,
    total_items: int,
    concern_bands: list[str] | None = None,
    max_total: int | None = None,
    likert_hi: int | None = None,
) -> None:
    fm = {
        "instrument": slug,
        "version": version,
        "run_timestamp": timestamp,
        "total_score": total,
        "band": band,
        "bandable": band is not None,
        "coverage": {
            "answered_at_high_confidence": answered,
            "total_items": total_items,
            "coverage_pct": coverage_pct,
            "bandable_threshold": 80.0,
        },
    }
    # Loader-surfaced geometry — omitted to simulate a pre-deepening report
    # (render_summary then recovers from the engine instrument definition).
    if likert_hi is not None:
        fm["likert"] = {"lo": 0, "hi": likert_hi}
    if max_total is not None:
        fm["max_total"] = max_total
    if concern_bands is not None:
        fm["concern_bands"] = concern_bands
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False).strip()
        + "\n---\n\n# Report body\n"
    )
    path.write_text(body, encoding="utf-8")


def _seed_study_runs(study_dir: Path, runs: list[dict]) -> None:
    """Build a synthetic study tree from a list of run-specs."""
    for run in runs:
        run_dir = study_dir / "runs" / run["timestamp"]
        inst_dir = run_dir / "instruments"
        inst_dir.mkdir(parents=True)
        for slug, fields in run["instruments"].items():
            _make_report(
                inst_dir / f"{slug}.md",
                slug=slug,
                version=fields.get("version", "1.0.0"),
                timestamp=run["timestamp"],
                total=fields["total"],
                band=fields.get("band"),
                coverage_pct=fields.get("coverage_pct", 100.0),
                answered=fields.get("answered", fields.get("total_items", 9)),
                total_items=fields.get("total_items", 9),
                concern_bands=fields.get("concern_bands"),
                max_total=fields.get("max_total"),
                likert_hi=fields.get("likert_hi"),
            )


class TestTimelineLoader:
    def test_empty_study_dir(self, tmp_path: Path) -> None:
        timeline = load_timeline(tmp_path / "nonexistent")
        assert timeline.n_runs == 0
        assert timeline.latest is None

    def test_single_run_one_instrument(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 8, "band": "mild", "total_items": 9},
                    },
                }
            ],
        )
        timeline = load_timeline(tmp_path)
        assert timeline.n_runs == 1
        latest = timeline.latest
        assert latest is not None
        assert "phq-9" in latest.instruments
        assert latest.instruments["phq-9"].total_score == 8
        assert latest.instruments["phq-9"].band == "mild"

    def test_multi_run_ordered_ascending(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-10T10-00-00",
                    "instruments": {"phq-9": {"total": 5, "band": "mild", "total_items": 9}},
                },
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {"phq-9": {"total": 8, "band": "mild", "total_items": 9}},
                },
            ],
        )
        timeline = load_timeline(tmp_path)
        assert timeline.n_runs == 2
        assert timeline.runs[0].timestamp == "2026-05-10T10-00-00"
        assert timeline.runs[1].timestamp == "2026-05-17T10-00-00"
        assert timeline.latest.timestamp == "2026-05-17T10-00-00"  # type: ignore[union-attr]
        assert timeline.previous.timestamp == "2026-05-10T10-00-00"  # type: ignore[union-attr]

    def test_skips_tmp_dirs(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {"phq-9": {"total": 5, "band": "mild", "total_items": 9}},
                }
            ],
        )
        # Add a stale tmp dir that should be ignored.
        stale = tmp_path / "runs" / ".2026-05-17T11-00-00.tmp"
        stale.mkdir()
        timeline = load_timeline(tmp_path)
        assert timeline.n_runs == 1

    def test_series_for_one_instrument(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": f"2026-05-{day:02d}T10-00-00",
                    "instruments": {
                        "phq-9": {"total": d, "band": "mild", "total_items": 9}
                    },
                }
                for day, d in [(10, 4), (15, 6), (17, 8)]
            ],
        )
        timeline = load_timeline(tmp_path)
        series = timeline.series_for("phq-9")
        assert [s.total_score for s in series] == [4, 6, 8]


class TestSnapshotGeometry:
    def test_carries_loader_surfaced_fields(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 12, "band": "moderate", "total_items": 9,
                                  "likert_hi": 3, "max_total": 27,
                                  "concern_bands": ["moderate", "severe"]},
                    },
                }
            ],
        )
        snap = load_timeline(tmp_path).latest.instruments["phq-9"]  # type: ignore[union-attr]
        assert snap.likert_hi == 3
        assert snap.max_total == 27
        assert snap.concern_bands == ("moderate", "severe")

    def test_old_report_defaults_to_none_and_empty(self, tmp_path: Path) -> None:
        _seed_study_runs(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 8, "band": "mild", "total_items": 9},
                    },
                }
            ],
        )
        snap = load_timeline(tmp_path).latest.instruments["phq-9"]  # type: ignore[union-attr]
        assert snap.likert_hi is None
        assert snap.max_total is None
        assert snap.concern_bands == ()


class TestSnapshotFromDir:
    def test_picks_up_in_progress_run(self, tmp_path: Path) -> None:
        tmp_run = tmp_path / ".inprogress.tmp"
        inst_dir = tmp_run / "instruments"
        inst_dir.mkdir(parents=True)
        _make_report(
            inst_dir / "phq-9.md",
            slug="phq-9",
            version="1.0.0",
            timestamp="2026-05-17T15-00-00",
            total=3,
            band=None,
            coverage_pct=44.4,
            answered=4,
            total_items=9,
        )
        snap = snapshot_from_dir(tmp_run, timestamp="2026-05-17T15-00-00")
        assert snap.timestamp == "2026-05-17T15-00-00"
        assert "phq-9" in snap.instruments
        assert snap.instruments["phq-9"].total_score == 3


class TestChartsSvg:
    def _assert_valid_svg(self, path: Path) -> str:
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert content.startswith("<svg") or "<svg " in content
        assert content.rstrip().endswith("</svg>")
        return content

    def test_sparkline_renders_with_2_points(self, tmp_path: Path) -> None:
        out = render_sparkline([10.0, 25.0, 50.0], tmp_path / "spark.svg", range_max=100.0)
        content = self._assert_valid_svg(out)
        # Polyline must be present with 3 points
        assert "<polyline" in content
        assert content.count(",") >= 2  # at least N-1 point pairs

    def test_sparkline_placeholder_on_single_point(self, tmp_path: Path) -> None:
        out = render_sparkline([42.0], tmp_path / "spark.svg")
        content = self._assert_valid_svg(out)
        assert "activates by run 2" in content

    def test_radar_renders_with_5_axes(self, tmp_path: Path) -> None:
        current = {
            "phq-9": 0.3,
            "gad-7": 0.2,
            "asrs-v1.1": 0.5,
            "who-5": 0.7,
            "k6": 0.1,
        }
        out = render_radar(current, tmp_path / "radar.svg")
        content = self._assert_valid_svg(out)
        # All axis labels present
        for name in current:
            assert name in content
        # Gridlines (concentric polygons) at 0.25/0.5/0.75/1.0 = 4 polygons,
        # plus 1 for current → at least 5 <polygon> tags
        assert content.count("<polygon") >= 5
        # Legend mentions "current"
        assert "current" in content

    def test_radar_overlay_when_previous_provided(self, tmp_path: Path) -> None:
        current = {"phq-9": 0.4, "gad-7": 0.3}
        previous = {"phq-9": 0.2, "gad-7": 0.1}
        out = render_radar(current, tmp_path / "radar.svg", previous=previous)
        content = self._assert_valid_svg(out)
        assert "stroke-dasharray" in content  # previous polygon is dashed
        assert "previous run" in content      # legend mentions previous

    def test_timeline_renders_multi_point(self, tmp_path: Path) -> None:
        series = [
            ("2026-05-10T10-00-00", 4.0, 100.0),
            ("2026-05-15T10-00-00", 6.0, 100.0),
            ("2026-05-17T10-00-00", 8.0, 100.0),
        ]
        out = render_timeline("phq-9", series, tmp_path / "tl.svg", score_max=27.0)
        content = self._assert_valid_svg(out)
        assert "phq-9" in content
        # Two polylines (score + coverage)
        assert content.count("<polyline") == 2

    def test_timeline_placeholder_when_single_point(self, tmp_path: Path) -> None:
        out = render_timeline(
            "phq-9",
            [("2026-05-17T10-00-00", 8.0, 100.0)],
            tmp_path / "tl.svg",
            score_max=27.0,
        )
        content = self._assert_valid_svg(out)
        assert "activates by run 2" in content


class TestRenderSummary:
    @pytest.fixture
    def two_run_study(self, tmp_path: Path) -> Path:
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-10T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 4, "band": "minimal", "coverage_pct": 44.4,
                                  "answered": 4, "total_items": 9},
                        "gad-7": {"total": 3, "band": "minimal", "coverage_pct": 57.1,
                                  "answered": 4, "total_items": 7},
                        "who-5": {"total": 18, "band": "moderate", "coverage_pct": 100.0,
                                  "answered": 5, "total_items": 5},
                    },
                },
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 6, "band": "mild", "coverage_pct": 44.4,
                                  "answered": 4, "total_items": 9},
                        "gad-7": {"total": 4, "band": "minimal", "coverage_pct": 57.1,
                                  "answered": 4, "total_items": 7},
                        "who-5": {"total": 15, "band": "moderate", "coverage_pct": 100.0,
                                  "answered": 5, "total_items": 5},
                    },
                },
            ],
        )
        return study_dir

    def test_summary_renders_with_2_runs(self, two_run_study: Path) -> None:
        timeline = load_timeline(two_run_study)
        summary_path = two_run_study / "runs" / "2026-05-17T10-00-00" / "_summary.md"
        charts_dir = two_run_study / "runs" / "2026-05-17T10-00-00" / "charts"

        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=summary_path,
            charts_dir=charts_dir,
        )
        assert out.is_file()
        content = out.read_text(encoding="utf-8")

        # Frontmatter present
        assert content.startswith("---\n")
        fm_end = content.index("\n---\n", 4)
        fm = yaml.safe_load(content[4:fm_end])
        assert fm["study_id"] == "longitudinal-baseline"
        assert fm["n_instruments"] == 3
        assert fm["n_runs_in_timeline"] == 2

        # Required sections
        for header in (
            "Cross-instrument current state",
            "Cross-instrument radar",
            "Coverage — wiki-health-meter",
            "Per-instrument trajectories",
            "Convergence / discrepancy flags",
        ):
            assert f"## {header}" in content, f"missing section: {header}"

        # Delta column populated (run 2 — should show deltas like +2 / +1 / -3)
        assert " | +2 |" in content or " | -3 |" in content

        # Chart references inline
        assert "(charts/radar.svg)" in content
        assert "(charts/coverage-sparkline.svg)" in content
        # Per-instrument timelines reference per-instrument SVGs
        assert "timeline-phq-9.svg" in content

        # Informant-banner included
        assert "Informant Report" in content

        # SVGs were actually written
        assert (charts_dir / "radar.svg").is_file()
        assert (charts_dir / "coverage-sparkline.svg").is_file()
        for slug in ("phq-9", "gad-7", "who-5"):
            assert (charts_dir / f"timeline-{slug}.svg").is_file()

    def test_summary_run_1_says_overlay_activates_by_run_2(self, tmp_path: Path) -> None:
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 6, "band": "mild", "coverage_pct": 44.4,
                                  "answered": 4, "total_items": 9},
                    },
                }
            ],
        )
        timeline = load_timeline(study_dir)
        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=study_dir / "runs" / "2026-05-17T10-00-00" / "_summary.md",
            charts_dir=study_dir / "runs" / "2026-05-17T10-00-00" / "charts",
        )
        content = out.read_text(encoding="utf-8")
        assert "First run" in content
        # Delta column shows em-dash for run 1
        assert "| — |" in content

    def test_flags_isi_olbi_pss10_from_frontmatter(self, tmp_path: Path) -> None:
        """The three instruments the old hardcoded severe_bands table could
        NEVER flag (isi / olbi / pss-10) now raise concern flags off their
        own `concern_bands` frontmatter — no per-slug table."""
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "isi": {"total": 25, "band": "severe", "coverage_pct": 100.0,
                                "answered": 7, "total_items": 7, "likert_hi": 4,
                                "max_total": 28,
                                "concern_bands": ["moderate", "severe"]},
                        "olbi": {"total": 70, "band": "very-high", "coverage_pct": 100.0,
                                 "answered": 16, "total_items": 16, "likert_hi": 5,
                                 "max_total": 80,
                                 "concern_bands": ["high", "very-high"]},
                        "pss-10": {"total": 30, "band": "high", "coverage_pct": 100.0,
                                   "answered": 10, "total_items": 10, "likert_hi": 4,
                                   "max_total": 40, "concern_bands": ["high"]},
                    },
                }
            ],
        )
        timeline = load_timeline(study_dir)
        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=study_dir / "runs" / "2026-05-17T10-00-00" / "_summary.md",
            charts_dir=study_dir / "runs" / "2026-05-17T10-00-00" / "charts",
        )
        content = out.read_text(encoding="utf-8")
        assert "`isi` band = **severe**" in content
        assert "`olbi` band = **very-high**" in content
        assert "`pss-10` band = **high**" in content
        assert "No automatic flags raised" not in content

    def test_flags_recovered_when_frontmatter_lacks_concern_bands(
        self, tmp_path: Path
    ) -> None:
        """OLD reports (pre-deepening) carry no `concern_bands` — the flag is
        recovered from the engine instrument definition so historical runs
        still surface elevated bands."""
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    # No concern_bands / max_total / likert_hi in frontmatter.
                    "instruments": {
                        "isi": {"total": 25, "band": "severe", "coverage_pct": 100.0,
                                "answered": 7, "total_items": 7},
                    },
                }
            ],
        )
        timeline = load_timeline(study_dir)
        # Snapshot has no concern_bands (old shape) …
        assert timeline.latest.instruments["isi"].concern_bands == ()  # type: ignore[union-attr]
        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=study_dir / "runs" / "2026-05-17T10-00-00" / "_summary.md",
            charts_dir=study_dir / "runs" / "2026-05-17T10-00-00" / "charts",
        )
        # … yet the flag is still raised via engine-definition recovery.
        assert "`isi` band = **severe**" in out.read_text(encoding="utf-8")

    def test_non_concern_band_not_flagged(self, tmp_path: Path) -> None:
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "isi": {"total": 3, "band": "no-clinical-insomnia",
                                "coverage_pct": 100.0, "answered": 7, "total_items": 7,
                                "likert_hi": 4, "max_total": 28,
                                "concern_bands": ["moderate", "severe"]},
                    },
                }
            ],
        )
        timeline = load_timeline(study_dir)
        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=study_dir / "runs" / "2026-05-17T10-00-00" / "_summary.md",
            charts_dir=study_dir / "runs" / "2026-05-17T10-00-00" / "charts",
        )
        content = out.read_text(encoding="utf-8")
        assert "band = **no-clinical-insomnia**" not in content
        assert "No automatic flags raised" in content

    def test_summary_flags_low_coverage_outlier(self, tmp_path: Path) -> None:
        """When one instrument's coverage is far below the others, summary
        surfaces it as a substrate-gap flag."""
        study_dir = tmp_path / "longitudinal-baseline"
        _seed_study_runs(
            study_dir,
            [
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "instruments": {
                        "phq-9": {"total": 4, "band": "minimal", "coverage_pct": 100.0,
                                  "answered": 9, "total_items": 9},
                        "k6": {"total": 2, "band": "minimal", "coverage_pct": 30.0,
                               "answered": 2, "total_items": 6},
                    },
                }
            ],
        )
        timeline = load_timeline(study_dir)
        out = render_summary(
            study_id="longitudinal-baseline",
            timeline=timeline,
            summary_path=study_dir / "runs" / "2026-05-17T10-00-00" / "_summary.md",
            charts_dir=study_dir / "runs" / "2026-05-17T10-00-00" / "charts",
        )
        content = out.read_text(encoding="utf-8")
        assert "substrate gap" in content
        assert "k6" in content
