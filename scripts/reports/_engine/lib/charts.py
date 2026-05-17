"""Pure-Python SVG chart renderers for the M019 meta-report.

Three chart types — sparkline, radar, timeline — that the
`_summary.md` references inline via `![title](charts/foo.svg)`.

Why SVG / why not matplotlib:
  - matplotlib adds ~30 MB + numpy as transitive deps for what
    are three geometrically-simple plots.
  - SVG is text-formatted, renders in Obsidian + GitHub
    markdown directly, and stays diff-friendly across runs.
  - All three plots are pure trig + string templates; no
    heavyweight tooling needed.
  - Operator can hand-edit / re-style a chart with a text editor
    if the engine output isn't quite right — closes the
    rendering-pipeline brittleness gap.

Scope-discipline: this module writes SVG files but reads only its
own arguments. No filesystem walks, no config access. The caller
(render_summary.py) does all the I/O orchestration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


# Visual tokens — kept in one place so the operator's later style
# adjustments don't need to chase variables across the file.
_PALETTE = {
    "ink": "#1f2937",         # default stroke + text
    "muted": "#9ca3af",       # gridlines + secondary labels
    "current": "#2563eb",     # current-run polygon stroke
    "current_fill": "rgba(37, 99, 235, 0.18)",
    "previous": "#9333ea",    # previous-run overlay stroke (dashed)
    "previous_fill": "rgba(147, 51, 234, 0.10)",
    "axis": "#d1d5db",
    "warn": "#dc2626",
}


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def _svg_header(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="system-ui, sans-serif">'
    )


def _placeholder(out_path: Path, width: int, height: int, message: str) -> Path:
    """Write a minimal SVG that says 'not enough data yet'."""
    body = (
        _svg_header(width, height)
        + f'<rect width="100%" height="100%" fill="#f9fafb" stroke="{_PALETTE["muted"]}"/>'
        + f'<text x="{width//2}" y="{height//2}" text-anchor="middle" '
          f'dominant-baseline="middle" fill="{_PALETTE["muted"]}" font-size="14">'
          f"{message}</text>"
        + "</svg>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path


# ── Sparkline ────────────────────────────────────────────────────────


def render_sparkline(
    series: list[float],
    out_path: Path,
    *,
    width: int = 200,
    height: int = 40,
    range_min: float = 0.0,
    range_max: float = 100.0,
) -> Path:
    """Tiny inline line graph for a 0..1 (or arbitrary-range) series.

    Designed for embedding `![coverage](charts/sparkline.svg)` next to
    a number. No axes, no labels — read it as a trend, not a measurement.
    """
    if len(series) < 2:
        return _placeholder(
            out_path, width, height, "single datapoint — sparkline activates by run 2"
        )

    span = max(range_max - range_min, 1e-9)
    pad = 4
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    n = len(series)

    def _coord(i: int, v: float) -> Point:
        x = pad + (inner_w * i / (n - 1))
        # SVG y grows downward — invert from value
        y = pad + inner_h * (1.0 - (v - range_min) / span)
        return Point(x, y)

    points = [_coord(i, v) for i, v in enumerate(series)]
    polyline = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in points)
    last = points[-1]

    body = (
        _svg_header(width, height)
        + f'<rect width="100%" height="100%" fill="white"/>'
        + f'<polyline points="{polyline}" fill="none" '
          f'stroke="{_PALETTE["current"]}" stroke-width="1.5"/>'
        + f'<circle cx="{last.x:.1f}" cy="{last.y:.1f}" r="2.5" '
          f'fill="{_PALETTE["current"]}"/>'
        + "</svg>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path


# ── Radar (cross-instrument current state) ──────────────────────────


def render_radar(
    current: dict[str, float],
    out_path: Path,
    *,
    previous: dict[str, float] | None = None,
    width: int = 360,
    height: int = 360,
    range_max: float = 1.0,
) -> Path:
    """Polar polygon plot with one axis per instrument.

    Values are expected pre-normalised to `[0, range_max]` (typically
    0..1 from instrument.total/max_total). The previous-run overlay
    activates when `previous` is non-empty — same axis order; missing
    keys plot as 0.
    """
    axes = sorted(current.keys())
    if not axes:
        return _placeholder(out_path, width, height, "no instruments to plot")

    cx, cy = width / 2, height / 2 - 10  # slight upward shift to make room for legend
    radius = min(width, height) / 2 - 60   # margin for axis labels

    def _polar(i: int, v_norm: float) -> Point:
        # Angle 0 at top, going clockwise.
        angle = 2 * math.pi * (i / len(axes)) - math.pi / 2
        r = radius * v_norm
        return Point(cx + r * math.cos(angle), cy + r * math.sin(angle))

    def _polygon(values: dict[str, float]) -> list[Point]:
        return [
            _polar(i, max(0.0, min(1.0, values.get(axis, 0.0) / range_max)))
            for i, axis in enumerate(axes)
        ]

    elements: list[str] = []

    # White background
    elements.append('<rect width="100%" height="100%" fill="white"/>')

    # Gridlines (concentric polygons at 0.25, 0.5, 0.75, 1.0)
    for level in (0.25, 0.5, 0.75, 1.0):
        pts = [_polar(i, level) for i in range(len(axes))]
        elements.append(
            f'<polygon points="{" ".join(f"{p.x:.1f},{p.y:.1f}" for p in pts)}" '
            f'fill="none" stroke="{_PALETTE["axis"]}" stroke-width="0.75"/>'
        )

    # Axis spokes
    for i in range(len(axes)):
        end = _polar(i, 1.0)
        elements.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
            f'x2="{end.x:.1f}" y2="{end.y:.1f}" '
            f'stroke="{_PALETTE["axis"]}" stroke-width="0.75"/>'
        )

    # Previous-run polygon (dashed, no fill highlight)
    if previous:
        prev_pts = _polygon(previous)
        elements.append(
            f'<polygon points="{" ".join(f"{p.x:.1f},{p.y:.1f}" for p in prev_pts)}" '
            f'fill="{_PALETTE["previous_fill"]}" stroke="{_PALETTE["previous"]}" '
            f'stroke-width="1.4" stroke-dasharray="5,3"/>'
        )

    # Current-run polygon (filled)
    curr_pts = _polygon(current)
    elements.append(
        f'<polygon points="{" ".join(f"{p.x:.1f},{p.y:.1f}" for p in curr_pts)}" '
        f'fill="{_PALETTE["current_fill"]}" stroke="{_PALETTE["current"]}" '
        f'stroke-width="1.8"/>'
    )

    # Dots at each current-polygon vertex (clarify discrete data points)
    for p in curr_pts:
        elements.append(
            f'<circle cx="{p.x:.1f}" cy="{p.y:.1f}" r="3" '
            f'fill="{_PALETTE["current"]}"/>'
        )

    # Axis labels — slightly outside the radius, anchor depends on x position
    for i, axis in enumerate(axes):
        anchor_pt = _polar(i, 1.18)
        anchor = "middle"
        if anchor_pt.x < cx - 5:
            anchor = "end"
        elif anchor_pt.x > cx + 5:
            anchor = "start"
        elements.append(
            f'<text x="{anchor_pt.x:.1f}" y="{anchor_pt.y:.1f}" '
            f'text-anchor="{anchor}" dominant-baseline="middle" '
            f'fill="{_PALETTE["ink"]}" font-size="12">{axis}</text>'
        )

    # Legend at bottom
    legend_y = height - 18
    elements.append(
        f'<rect x="{cx - 90}" y="{legend_y - 8}" width="10" height="10" '
        f'fill="{_PALETTE["current_fill"]}" stroke="{_PALETTE["current"]}"/>'
        f'<text x="{cx - 75}" y="{legend_y}" fill="{_PALETTE["ink"]}" '
        f'font-size="11">current</text>'
    )
    if previous:
        elements.append(
            f'<rect x="{cx + 10}" y="{legend_y - 8}" width="10" height="10" '
            f'fill="{_PALETTE["previous_fill"]}" stroke="{_PALETTE["previous"]}" '
            f'stroke-dasharray="2,2"/>'
            f'<text x="{cx + 25}" y="{legend_y}" fill="{_PALETTE["ink"]}" '
            f'font-size="11">previous run</text>'
        )

    body = _svg_header(width, height) + "".join(elements) + "</svg>"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path


# ── Per-instrument timeline (score + coverage double-line) ──────────


def render_timeline(
    label: str,
    series: list[tuple[str, float, float]],
    out_path: Path,
    *,
    width: int = 480,
    height: int = 180,
    score_max: float = 1.0,
) -> Path:
    """Multi-point line plot of (timestamp, score, coverage_pct).

    Score is plotted relative to `score_max` (normalised 0..1).
    Coverage is plotted 0..100 on the same 0..1 axis as score/score_max.
    Two stroked lines + dots; date stamps along the bottom (just the
    YYYY-MM-DD prefix; HH-MM-SS truncated for readability).
    """
    if len(series) < 2:
        return _placeholder(
            out_path,
            width,
            height,
            f"{label}: timeline activates by run 2",
        )

    pad_top, pad_bot, pad_l, pad_r = 20, 30, 40, 12
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_top - pad_bot
    n = len(series)

    def _coord(i: int, v_norm: float) -> Point:
        x = pad_l + (inner_w * i / (n - 1))
        y = pad_top + inner_h * (1.0 - v_norm)
        return Point(x, y)

    score_norm = [
        max(0.0, min(1.0, s / score_max if score_max > 0 else 0.0))
        for (_, s, _) in series
    ]
    cov_norm = [max(0.0, min(1.0, c / 100.0)) for (_, _, c) in series]
    score_pts = [_coord(i, v) for i, v in enumerate(score_norm)]
    cov_pts = [_coord(i, v) for i, v in enumerate(cov_norm)]

    elements: list[str] = []
    elements.append('<rect width="100%" height="100%" fill="white"/>')

    # Plot frame
    elements.append(
        f'<rect x="{pad_l}" y="{pad_top}" width="{inner_w}" height="{inner_h}" '
        f'fill="none" stroke="{_PALETTE["axis"]}" stroke-width="0.5"/>'
    )

    # Title
    elements.append(
        f'<text x="{pad_l}" y="14" fill="{_PALETTE["ink"]}" '
        f'font-size="12" font-weight="600">{label}</text>'
    )

    # Coverage line (background, lighter)
    cov_polyline = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in cov_pts)
    elements.append(
        f'<polyline points="{cov_polyline}" fill="none" '
        f'stroke="{_PALETTE["muted"]}" stroke-width="1.2" '
        f'stroke-dasharray="4,2"/>'
    )

    # Score line (foreground)
    score_polyline = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in score_pts)
    elements.append(
        f'<polyline points="{score_polyline}" fill="none" '
        f'stroke="{_PALETTE["current"]}" stroke-width="1.8"/>'
    )

    # Dots at each score point
    for p in score_pts:
        elements.append(
            f'<circle cx="{p.x:.1f}" cy="{p.y:.1f}" r="2.5" '
            f'fill="{_PALETTE["current"]}"/>'
        )

    # X-axis labels (compact dates — every other tick if many points)
    every = max(1, n // 5)
    for i, (ts, _, _) in enumerate(series):
        if i % every and i != n - 1:
            continue
        # YYYY-MM-DD from "YYYY-MM-DDTHH-MM-SS"
        short = ts.split("T")[0] if "T" in ts else ts[:10]
        x_lab = _coord(i, 0.0).x
        elements.append(
            f'<text x="{x_lab:.1f}" y="{height - 14}" text-anchor="middle" '
            f'fill="{_PALETTE["muted"]}" font-size="9">{short}</text>'
        )

    # Y-axis labels (0, score_max, 100% coverage indicator)
    elements.append(
        f'<text x="{pad_l - 6}" y="{pad_top + 4}" text-anchor="end" '
        f'fill="{_PALETTE["muted"]}" font-size="9">max</text>'
        f'<text x="{pad_l - 6}" y="{pad_top + inner_h + 2}" text-anchor="end" '
        f'fill="{_PALETTE["muted"]}" font-size="9">0</text>'
    )

    # Mini legend (top-right)
    legend_x = width - 100
    elements.append(
        f'<line x1="{legend_x}" y1="14" x2="{legend_x + 14}" y2="14" '
        f'stroke="{_PALETTE["current"]}" stroke-width="1.8"/>'
        f'<text x="{legend_x + 18}" y="17" fill="{_PALETTE["ink"]}" '
        f'font-size="9">score</text>'
    )
    elements.append(
        f'<line x1="{legend_x + 50}" y1="14" x2="{legend_x + 64}" y2="14" '
        f'stroke="{_PALETTE["muted"]}" stroke-width="1.2" stroke-dasharray="3,2"/>'
        f'<text x="{legend_x + 68}" y="17" fill="{_PALETTE["ink"]}" '
        f'font-size="9">cov%</text>'
    )

    body = _svg_header(width, height) + "".join(elements) + "</svg>"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path
