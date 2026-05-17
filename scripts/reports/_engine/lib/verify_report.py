"""Embedded-methodology verification for per-instrument reports.

The Q6 future-fit posture (DECISIONS.md 2026-05-17) requires that
every per-instrument report be **durable independent of the engine**:
items, scoring rules, cutoffs, model_id, prompt_version, scope-spec,
and per-item evidence must all be present inline (collapsible
`<details>` blocks are fine; absence is not).

This module verifies a freshly-rendered report against that
contract. The runner calls it after writing each per-instrument
report; failures are surfaced as warnings (wedge) rather than hard
errors so a single bad report doesn't block the whole run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


# Required frontmatter keys. Top-level only — nested keys like
# `coverage.coverage_pct` are checked separately.
REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = (
    "instrument",
    "version",
    "run_timestamp",
    "total_score",
    "model_id",
    "prompt_version",
    "scope",
    "coverage",
)

# Required body sections — checked by markdown heading text. Trailing
# colon/whitespace tolerated.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "Score",
    "Items",
    "Per-item detail",
    "Embedded methodology",
)

# Required embedded-methodology subsections (collapsible <details>).
# Verified by the `<summary>` text.
REQUIRED_METHODOLOGY_SUMMARIES: tuple[str, ...] = (
    "Items (verbatim from items.yaml)",
    "Cutoffs (verbatim from cutoffs.yaml)",
    "Instrument meta (verbatim from instrument.yaml)",
    "Prompt rendered for this run",
    "Scope-resolved substrate paths",
)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    missing: tuple[str, ...]

    @property
    def summary(self) -> str:
        if self.ok:
            return "report passes embedded-methodology checks"
        return f"missing {len(self.missing)} required field(s): " + ", ".join(self.missing)


def verify_report(report_path: Path) -> VerificationResult:
    """Check that a per-instrument report has every required field.

    Returns `VerificationResult(ok, missing)`. `missing` lists every
    required field (frontmatter key OR section heading OR collapsible
    summary text) that is NOT present.
    """
    if not report_path.is_file():
        return VerificationResult(ok=False, missing=("(file does not exist)",))

    text = report_path.read_text(encoding="utf-8")
    missing: list[str] = []

    # Frontmatter parse
    fm = _extract_frontmatter(text)
    if fm is None:
        missing.append("(no parseable YAML frontmatter)")
        return VerificationResult(ok=False, missing=tuple(missing))
    for key in REQUIRED_FRONTMATTER_KEYS:
        if key not in fm:
            missing.append(f"frontmatter.{key}")

    # Informant-report banner — wedge contract: every report carries it
    if "Informant Report" not in text:
        missing.append("informant-report banner")

    # Markdown section headers
    for section in REQUIRED_SECTIONS:
        if not _has_section(text, section):
            missing.append(f"section: {section}")

    # Embedded methodology collapsible summaries
    for sub in REQUIRED_METHODOLOGY_SUMMARIES:
        if f"<summary>{sub}" not in text:
            missing.append(f"details-block: {sub}")

    return VerificationResult(ok=not missing, missing=tuple(missing))


def _extract_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    pattern = re.compile(r"^---\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return None
    block = text[matches[0].end():matches[1].start()]
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _has_section(text: str, section: str) -> bool:
    """True if the markdown text has a `## <section>` heading anywhere."""
    pattern = re.compile(rf"^##\s+{re.escape(section)}\s*$", re.MULTILINE)
    return bool(pattern.search(text))
