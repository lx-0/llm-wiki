"""Deterministic meta-report renderer for one study-run.

Reads the cross-run timeline + the freshly-written per-instrument
reports + the manifest. Writes:

  <run-dir>/_summary.md
  <run-dir>/charts/radar.svg
  <run-dir>/charts/coverage-sparkline.svg
  <run-dir>/charts/timeline-<slug>.svg   (one per instrument)

The meta-report shape (per M019-CONTEXT.md exit criteria #5):

  1. Frontmatter: study_id, run_timestamp, n_instruments, n_runs.
  2. Informant-report banner (Q3 from CONTEXT).
  3. Cross-instrument current-state table (slug | score | band |
     coverage% | delta-vs-previous) — delta omitted on run 1.
  4. Inline radar chart (current state, with previous-run overlay
     activating on run 2+).
  5. Coverage sparkline over runs (activates by run 2).
  6. Per-instrument timeline links + thumbnails (activates by run 2).
  7. Convergence / discrepancy flags across instruments (S05 will
     enrich; wedge writes a stub section listing where bands suggest
     consistency or divergence).

This is the PRIMARY consumption surface per the operator's Q1
office-hours answer ("meistens lese ich nur den aktuellsten Report,
... ein meta report, der veraenderungen bestenfalls grafisch zeigt
waere auch cool"). Per-instrument detail reports are infrastructure.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.reports._engine.lib.charts import (
    render_radar,
    render_sparkline,
    render_timeline,
)
from scripts.reports._engine.lib.timeline import (
    InstrumentSnapshot,
    RunSnapshot,
    Timeline,
)


_INFORMANT_BANNER = (
    "> **Informant Report — methodology summary.** Scores below were inferred "
    "by an LLM observer reading the operator's substrate (daily logs, voice "
    "notes, health data, transcripts) over each instrument's lookback window. "
    "This is **not** self-report. Embedded methodology lives in each per-"
    "instrument report under `instruments/<slug>.md`; this meta-report is the "
    "across-instrument summary. To run a self-report-form study for cross-"
    "validation, fork with `source: form` (lands post-wedge).\n"
)


def _normalise(score: int, max_total: int) -> float:
    if max_total <= 0:
        return 0.0
    return max(0.0, min(1.0, score / max_total))


def _format_delta(curr: int, prev: int | None) -> str:
    if prev is None:
        return "—"
    delta = curr - prev
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}"


def _instrument_max(snap: InstrumentSnapshot) -> int:
    """Best-effort max total: total_items × highest answer.

    The snapshot doesn't carry the likert hi explicitly, but we can
    recover it from coverage's known fields plus the band-cutoffs.
    For wedge instruments PHQ-9 (27), GAD-7 (21), ASRS-v1.1 (72),
    WHO-5 (25), K6 (24) — but those numbers aren't in the snapshot.
    We back-compute from total_items × an assumed scale ceiling read
    from per-instrument heuristic: derived from the slug here.
    """
    # Hard-coded for wedge — post-wedge will move this into a loader-
    # populated field on InstrumentSnapshot. For wedge cleanliness it's
    # acceptable to keep the table here next to its only consumer.
    SLUG_TO_MAX = {
        "phq-9": 27,
        "gad-7": 21,
        "asrs-v1.1": 72,
        "who-5": 25,
        "k6": 24,
        "pss-10": 40,  # 10 items × 0-4 scale; M019+ rebalance
        "isi": 28,     # 7 items × 0-4 scale; M019+ sleep-screen expansion
        "olbi": 80,    # 16 items × 1-5 scale; M019+ burnout-screen expansion (range 16-80)
        "meq-19": 86,  # placeholder for future MEQ wiring
    }
    # Snapshot's `slug` is alias-or-filename — match the wedge canonical
    # slug by suffix-stripping known alias patterns. Falls back to the
    # naive product if unknown.
    canonical = snap.slug
    for known in SLUG_TO_MAX:
        if canonical == known or canonical.startswith(known + "-"):
            return SLUG_TO_MAX[known]
    return max(snap.total_items, 1)


def _build_radar_data(snapshot: RunSnapshot) -> dict[str, float]:
    """Normalise each instrument's score to 0..1 for radar plot."""
    return {
        s.slug: _normalise(s.total_score, _instrument_max(s))
        for s in snapshot.instruments.values()
    }


def _build_coverage_series(timeline: Timeline) -> list[float]:
    """Average coverage_pct across instruments per run, time-ordered."""
    series: list[float] = []
    for run in timeline.runs:
        if not run.instruments:
            series.append(0.0)
            continue
        avg = sum(s.coverage_pct for s in run.instruments.values()) / len(
            run.instruments
        )
        series.append(avg)
    return series


def _render_per_instrument_timelines(
    timeline: Timeline,
    charts_dir: Path,
) -> dict[str, Path]:
    """Write one timeline SVG per instrument; return slug → path map."""
    out: dict[str, Path] = {}
    for key in timeline.all_instrument_keys():
        snapshots = timeline.series_for(key)
        if not snapshots:
            continue
        series: list[tuple[str, float, float]] = [
            (s.timestamp, float(s.total_score), s.coverage_pct)
            for s in snapshots
        ]
        max_total = _instrument_max(snapshots[-1])
        out_path = charts_dir / f"timeline-{key}.svg"
        render_timeline(
            label=key,
            series=series,
            out_path=out_path,
            score_max=float(max_total),
        )
        out[key] = out_path
    return out


def _per_item_likert_hi(snap: InstrumentSnapshot) -> int:
    """Best-effort likert.hi recovery: max_total / total_items. Works
    for instruments where every item has the same scale (current wedge
    + post-wedge). Falls back to 4 (most common) if division fails."""
    if snap.total_items <= 0:
        return 4
    return max(1, _instrument_max(snap) // snap.total_items)


def _render_per_instrument_radars(
    timeline: Timeline,
    charts_dir: Path,
) -> dict[str, Path]:
    """Write per-item radar SVG per instrument; return slug → path map.

    Axis = item id, vertex distance from center = item's normalised
    value (0..1). Previous-run polygon overlaid as dashed when
    available. Only renders for instruments whose latest snapshot has
    per_item data (older runs predating the per_item frontmatter
    addition produce placeholder)."""
    out: dict[str, Path] = {}
    latest = timeline.latest
    previous = timeline.previous
    if latest is None:
        return out
    for slug, snap in latest.instruments.items():
        out_path = charts_dir / f"radar-{slug}.svg"
        if not snap.per_item:
            # No per_item data — predates the runner extension.
            # Render placeholder so the link works.
            from scripts.reports._engine.lib.charts import _placeholder
            _placeholder(out_path, 360, 360,
                         f"{slug}: per-item data unavailable (older run schema)")
            out[slug] = out_path
            continue
        hi = _per_item_likert_hi(snap)
        current_data = {
            iid: max(0.0, min(1.0, val / hi))
            for iid, val in snap.per_item.items()
        }
        previous_data = None
        if previous and slug in previous.instruments:
            prev_snap = previous.instruments[slug]
            if prev_snap.per_item:
                prev_hi = _per_item_likert_hi(prev_snap)
                previous_data = {
                    iid: max(0.0, min(1.0, val / prev_hi))
                    for iid, val in prev_snap.per_item.items()
                }
        render_radar(current_data, out_path, previous=previous_data)
        out[slug] = out_path
    return out


def render_summary(
    *,
    study_id: str,
    timeline: Timeline,
    summary_path: Path,
    charts_dir: Path,
) -> Path:
    """Write `_summary.md` + chart SVGs for the latest run.

    The latest run's snapshots must already be in `timeline.latest`
    — callers (runner.cmd_run) load the timeline AFTER atomic-renaming
    the new run's tmp dir into final, so the timeline includes it.

    Args:
        study_id: study slug.
        timeline: cross-run aggregate including the just-completed run.
        summary_path: target path for `_summary.md` (typically inside
            the run's tmp dir before atomic commit).
        charts_dir: target path for chart SVGs (typically
            `<run-tmp>/charts/`).

    Returns:
        Path to the written `_summary.md`.
    """
    latest = timeline.latest
    previous = timeline.previous

    if latest is None or not latest.instruments:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            "# (empty run — no per-instrument reports were persisted)\n",
            encoding="utf-8",
        )
        return summary_path

    # 1. Radar (always renderable from 1+ runs)
    radar_path = charts_dir / "radar.svg"
    current_data = _build_radar_data(latest)
    previous_data = _build_radar_data(previous) if previous else None
    render_radar(current_data, radar_path, previous=previous_data)

    # 2. Coverage sparkline (placeholder on run 1; activates on run 2)
    cov_series = _build_coverage_series(timeline)
    sparkline_path = charts_dir / "coverage-sparkline.svg"
    render_sparkline(cov_series, sparkline_path, range_max=100.0)

    # 3. Per-instrument timelines
    per_inst_timelines = _render_per_instrument_timelines(timeline, charts_dir)

    # 4. Per-instrument radars (item-level breakdown — each axis is one item)
    per_inst_radars = _render_per_instrument_radars(timeline, charts_dir)

    # 4. Frontmatter
    bandable_count = sum(1 for s in latest.instruments.values() if s.bandable)
    avg_cov = (
        sum(s.coverage_pct for s in latest.instruments.values())
        / len(latest.instruments)
    )
    fm = {
        "kind": "meta-report",
        "study_id": study_id,
        "run_timestamp": latest.timestamp,
        "n_instruments": len(latest.instruments),
        "n_runs_in_timeline": timeline.n_runs,
        "n_bandable": bandable_count,
        "avg_coverage_pct": round(avg_cov, 1),
        "informant_report": True,
        "engine_version": "M019-S04",
    }

    lines: list[str] = []
    lines.append("---")
    lines.append(yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip())
    lines.append("---\n")

    lines.append(f"# {study_id} — {latest.timestamp} (run {timeline.n_runs})\n")
    lines.append(_INFORMANT_BANNER)

    # Cross-instrument table
    lines.append("## Cross-instrument current state\n")
    lines.append(
        "| Instrument | Score | Band | Coverage | Δ vs. previous |"
    )
    lines.append("|---|---|---|---|---|")
    prev_snapshots = previous.instruments if previous else {}
    for key in sorted(latest.instruments.keys()):
        snap = latest.instruments[key]
        prev_score = (
            prev_snapshots[key].total_score if key in prev_snapshots else None
        )
        delta = _format_delta(snap.total_score, prev_score)
        band = snap.band or "*partial*"
        max_total = _instrument_max(snap)
        lines.append(
            f"| {key} | {snap.total_score} / {max_total} | {band} | "
            f"{snap.coverage_pct}% | {delta} |"
        )
    lines.append("")

    # Radar chart inline
    lines.append("## Cross-instrument radar\n")
    radar_rel = radar_path.relative_to(summary_path.parent)
    if previous:
        lines.append(
            "Current run (solid) overlaid on the previous run (dashed). "
            "Each axis is one instrument, normalised 0..1 against its "
            "published total range.\n"
        )
    else:
        lines.append(
            "First run — only current-state polygon. Previous-run overlay "
            "(change-visualisation) activates by run 2.\n"
        )
    lines.append(f"![cross-instrument radar]({radar_rel})\n")

    # Coverage sparkline
    lines.append("## Coverage — wiki-health-meter\n")
    if timeline.n_runs >= 2:
        lines.append(
            f"Average inferred-coverage across all instruments, run-over-run. "
            f"This rising trend is the visible measure of the wiki growing "
            f"into the instruments. Latest avg: **{avg_cov:.1f}%** "
            f"({bandable_count} of {len(latest.instruments)} instruments "
            f"reached the bandable threshold).\n"
        )
        cov_rel = sparkline_path.relative_to(summary_path.parent)
        lines.append(f"![coverage sparkline]({cov_rel})\n")
    else:
        lines.append(
            f"Single run — sparkline activates by run 2. "
            f"Current avg coverage: **{avg_cov:.1f}%** "
            f"({bandable_count} of {len(latest.instruments)} bandable).\n"
        )

    # Per-instrument trajectories: timeline (over runs) + radar (over items)
    lines.append("## Per-instrument trajectories\n")
    for key in sorted(set(per_inst_timelines.keys()) | set(per_inst_radars.keys())):
        lines.append(f"### {key}\n")
        # Item-level radar (always renders from latest snapshot's per_item)
        if key in per_inst_radars:
            rel = per_inst_radars[key].relative_to(summary_path.parent)
            lines.append(f"**Item-level breakdown** — each axis is one item, "
                         f"vertex distance from center = item's normalised value "
                         f"(0..1). Dashed overlay = previous run when available.\n")
            lines.append(f"![{key} per-item radar]({rel})\n")
        # Run-over-run timeline (activates from run 2)
        if key in per_inst_timelines:
            rel = per_inst_timelines[key].relative_to(summary_path.parent)
            label = "Run-over-run timeline"
            if timeline.n_runs < 2:
                label += " (activates by run 2)"
            lines.append(f"**{label}**\n")
            lines.append(f"![{key} timeline]({rel})\n")

    # Convergence / discrepancy stub for S05 enrichment.
    lines.append("## Convergence / discrepancy flags\n")
    flags = _crosscheck_flags(latest)
    if flags:
        for flag in flags:
            lines.append(f"- {flag}")
        lines.append("")
    else:
        lines.append(
            "No automatic flags raised. S05's analyst-agent layer will "
            "enrich this section with interpretive cross-instrument "
            "synthesis.\n"
        )

    # Pointer to per-instrument detail
    lines.append("## Per-instrument detail\n")
    lines.append("Each instrument's full report with embedded methodology lives at:\n")
    for key in sorted(latest.instruments.keys()):
        lines.append(f"- `instruments/{key}.md`")
    lines.append("")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def _crosscheck_flags(snapshot: RunSnapshot) -> list[str]:
    """Wedge crosscheck — purely structural. S05 layer adds interpretive."""
    flags: list[str] = []
    # Find instruments that registered concerning band labels.
    severe_bands = {
        "phq-9": ("moderate", "moderately-severe", "severe"),
        "gad-7": ("moderate", "severe"),
        "who-5": ("poor", "low"),
        "k6": ("high", "very-high"),
    }
    for slug, snap in snapshot.instruments.items():
        for known, bands_of_concern in severe_bands.items():
            if (slug == known or slug.startswith(known + "-")) and snap.band in bands_of_concern:
                flags.append(
                    f"⚠️ `{slug}` band = **{snap.band}** "
                    f"(score {snap.total_score}, coverage {snap.coverage_pct}%)"
                )

    # Coverage outlier: if one instrument's coverage is dramatically lower
    # than the others, flag it — substrate gap for that domain.
    covs = [(s.slug, s.coverage_pct) for s in snapshot.instruments.values()]
    if len(covs) >= 2:
        avg = sum(c for _, c in covs) / len(covs)
        for slug, cov in covs:
            if avg - cov >= 25:
                flags.append(
                    f"ℹ️ `{slug}` coverage {cov}% is {avg - cov:.0f}pp below "
                    f"the cross-instrument average ({avg:.0f}%) — substrate "
                    f"gap for this domain"
                )
    return flags
