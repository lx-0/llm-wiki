"""Cross-run aggregation for one study's per-instrument reports.

Walks `<study>/runs/<ts>/instruments/<slug>.md`, parses each report's
frontmatter (written by S02-T04's runner), and yields a `Timeline`
object that the meta-report renderer + chart-writers consume.

Per-instrument frontmatter fields the timeline reads:
  - instrument (slug)
  - version
  - run_timestamp
  - total_score (int)
  - band (str | None)
  - bandable (bool)
  - coverage.coverage_pct (float)
  - coverage.answered_at_high_confidence (int)
  - coverage.total_items (int)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class InstrumentSnapshot:
    """One per-instrument score at one timestamp."""

    slug: str                  # may be alias-derived from filename
    version: str
    timestamp: str             # ISO-style with hyphens for filesystem safety
    total_score: int
    band: str | None
    bandable: bool
    coverage_pct: float
    answered: int
    total_items: int


@dataclass
class RunSnapshot:
    """All instrument snapshots from a single timestamped run."""

    timestamp: str
    instruments: dict[str, InstrumentSnapshot] = field(default_factory=dict)

    @property
    def instrument_slugs(self) -> list[str]:
        return sorted(self.instruments.keys())


@dataclass
class Timeline:
    """Cross-run aggregate for one study, ordered oldest → newest."""

    study_id: str
    runs: list[RunSnapshot] = field(default_factory=list)

    @property
    def n_runs(self) -> int:
        return len(self.runs)

    @property
    def latest(self) -> RunSnapshot | None:
        return self.runs[-1] if self.runs else None

    @property
    def previous(self) -> RunSnapshot | None:
        """Previous-to-latest run, or None when only ≤1 run exists."""
        return self.runs[-2] if len(self.runs) >= 2 else None

    def series_for(self, instrument_key: str) -> list[InstrumentSnapshot]:
        """Time-ordered series of snapshots for one instrument key
        (alias-or-slug)."""
        return [
            r.instruments[instrument_key]
            for r in self.runs
            if instrument_key in r.instruments
        ]

    def all_instrument_keys(self) -> list[str]:
        """Union of instrument keys across all runs, sorted."""
        keys: set[str] = set()
        for r in self.runs:
            keys.update(r.instruments.keys())
        return sorted(keys)


_FM_BOUNDARY = re.compile(r"^---\s*$", re.MULTILINE)


def _parse_frontmatter(markdown_text: str) -> dict | None:
    """Pull the YAML frontmatter block out of a markdown string.

    Returns the parsed dict or None if there's no leading `---` block.
    """
    if not markdown_text.startswith("---"):
        return None
    # Find the second `---` line
    matches = list(_FM_BOUNDARY.finditer(markdown_text))
    if len(matches) < 2:
        return None
    fm_start = matches[0].end()
    fm_end = matches[1].start()
    try:
        return yaml.safe_load(markdown_text[fm_start:fm_end])
    except yaml.YAMLError:
        return None


def _snapshot_from_report(report_path: Path) -> InstrumentSnapshot | None:
    """Load one per-instrument report's frontmatter into a snapshot."""
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _parse_frontmatter(text)
    if not isinstance(fm, dict):
        return None
    # filename without `.md` is the alias/slug. Prefer this over the
    # frontmatter `instrument` field because the manifest may have set
    # an alias that differs from slug.
    instrument_key = report_path.stem
    coverage = fm.get("coverage") or {}
    if not isinstance(coverage, dict):
        coverage = {}
    try:
        return InstrumentSnapshot(
            slug=instrument_key,
            version=str(fm.get("version", "")),
            timestamp=str(fm.get("run_timestamp", "")),
            total_score=int(fm.get("total_score", 0)),
            band=(str(fm["band"]) if fm.get("band") else None),
            bandable=bool(fm.get("bandable", False)),
            coverage_pct=float(coverage.get("coverage_pct", 0.0)),
            answered=int(coverage.get("answered_at_high_confidence", 0)),
            total_items=int(coverage.get("total_items", 0)),
        )
    except (TypeError, ValueError):
        return None


def snapshot_from_dir(ts_dir: Path, *, timestamp: str | None = None) -> RunSnapshot:
    """Build a RunSnapshot from a single timestamped run directory.

    Useful for picking up the in-progress run from a `RunDirectory`'s
    tmp dir before the atomic rename — the timeline can then include
    it as the newest snapshot. `timestamp` overrides the directory
    name (passed when ts_dir is a `.<ts>.tmp` form).
    """
    snap = RunSnapshot(timestamp=timestamp or ts_dir.name)
    instruments_dir = ts_dir / "instruments"
    if instruments_dir.is_dir():
        for report in sorted(instruments_dir.glob("*.md")):
            s = _snapshot_from_report(report)
            if s is not None:
                snap.instruments[s.slug] = s
    return snap


def load_timeline(study_dir: Path) -> Timeline:
    """Walk `<study_dir>/runs/<ts>/instruments/*.md` and build a Timeline.

    Runs are ordered ASC by the timestamp dir name (lexical sort works
    because the runner uses `%Y-%m-%dT%H-%M-%S` UTC). Runs with no
    parseable per-instrument reports are still represented as empty
    `RunSnapshot` so n_runs reflects ground truth.
    """
    study_id = study_dir.name
    runs_dir = study_dir / "runs"
    if not runs_dir.is_dir():
        return Timeline(study_id=study_id)

    runs: list[RunSnapshot] = []
    for ts_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        # Skip atomic-write tmp dirs (leading dot per study.py convention).
        if ts_dir.name.startswith("."):
            continue
        snap = RunSnapshot(timestamp=ts_dir.name)
        instruments_dir = ts_dir / "instruments"
        if instruments_dir.is_dir():
            for report in sorted(instruments_dir.glob("*.md")):
                s = _snapshot_from_report(report)
                if s is not None:
                    snap.instruments[s.slug] = s
        runs.append(snap)
    return Timeline(study_id=study_id, runs=runs)
