"""Tests for `lib/verify_report.py` — embedded-methodology contract."""

from __future__ import annotations

from pathlib import Path

from scripts.reports._engine.lib.verify_report import (
    REQUIRED_FRONTMATTER_KEYS,
    REQUIRED_METHODOLOGY_SUMMARIES,
    REQUIRED_SECTIONS,
    verify_report,
)


GOOD_REPORT_TEMPLATE = """\
---
instrument: phq-9
version: 1.0.0
title: Patient Health Questionnaire-9
domain: depression
run_timestamp: 2026-05-17T15-30-04
total_score: 3
band: null
coverage:
  answered_at_high_confidence: 4
  total_items: 9
  coverage_pct: 44.4
scope:
  lookback_days: 14
  globs: []
model_id: claude-haiku-4-5
prompt_version: 766ab8bc40763ec4
cost_usd: 0.17
---

# Patient Health Questionnaire-9 — 2026-05-17

> **Informant Report.** body banner …

## Score

- Total: 3 / 27

## Items

| ID | answer | ... |

## Per-item detail

### Item 1

Reasoning ...

## Embedded methodology

<details><summary>Items (verbatim from items.yaml)</summary>

```yaml
items
```
</details>

<details><summary>Cutoffs (verbatim from cutoffs.yaml)</summary>

```yaml
cutoffs
```
</details>

<details><summary>Instrument meta (verbatim from instrument.yaml)</summary>

```yaml
instrument
```
</details>

<details><summary>Prompt rendered for this run</summary>

```
prompt
```
</details>

<details><summary>Scope-resolved substrate paths</summary>

- daily/2026-05-17.md
</details>
"""


def _write(tmp_path: Path, content: str) -> Path:
    out = tmp_path / "phq-9.md"
    out.write_text(content, encoding="utf-8")
    return out


def test_good_report_passes(tmp_path: Path) -> None:
    out = _write(tmp_path, GOOD_REPORT_TEMPLATE)
    result = verify_report(out)
    assert result.ok, result.summary


def test_missing_frontmatter_key_flagged(tmp_path: Path) -> None:
    # Drop the `prompt_version` line
    bad = "\n".join(
        line for line in GOOD_REPORT_TEMPLATE.splitlines()
        if not line.startswith("prompt_version:")
    )
    out = _write(tmp_path, bad)
    result = verify_report(out)
    assert not result.ok
    assert "frontmatter.prompt_version" in result.missing


def test_missing_section_flagged(tmp_path: Path) -> None:
    # Drop the "## Embedded methodology" line
    bad = "\n".join(
        line for line in GOOD_REPORT_TEMPLATE.splitlines()
        if line.strip() != "## Embedded methodology"
    )
    out = _write(tmp_path, bad)
    result = verify_report(out)
    assert not result.ok
    assert "section: Embedded methodology" in result.missing


def test_missing_methodology_subsection_flagged(tmp_path: Path) -> None:
    bad = GOOD_REPORT_TEMPLATE.replace(
        "<summary>Cutoffs (verbatim from cutoffs.yaml)",
        "<summary>Cutoffs Banding Strategy",
    )
    out = _write(tmp_path, bad)
    result = verify_report(out)
    assert not result.ok
    assert any("details-block: Cutoffs" in m for m in result.missing)


def test_missing_informant_banner_flagged(tmp_path: Path) -> None:
    bad = GOOD_REPORT_TEMPLATE.replace("Informant Report", "Self Report")
    out = _write(tmp_path, bad)
    result = verify_report(out)
    assert not result.ok
    assert "informant-report banner" in result.missing


def test_no_frontmatter_at_all(tmp_path: Path) -> None:
    bad = "# Some Report\n\nBody without frontmatter.\n"
    out = _write(tmp_path, bad)
    result = verify_report(out)
    assert not result.ok
    assert "(no parseable YAML frontmatter)" in result.missing


def test_missing_file(tmp_path: Path) -> None:
    result = verify_report(tmp_path / "nonexistent.md")
    assert not result.ok


def test_required_lists_locked() -> None:
    """Pin the required lists so a silent edit surfaces here."""
    assert set(REQUIRED_FRONTMATTER_KEYS) == {
        "instrument", "version", "run_timestamp", "total_score",
        "model_id", "prompt_version", "scope", "coverage",
    }
    assert set(REQUIRED_SECTIONS) == {
        "Score", "Items", "Per-item detail", "Embedded methodology",
    }
    assert set(REQUIRED_METHODOLOGY_SUMMARIES) == {
        "Items (verbatim from items.yaml)",
        "Cutoffs (verbatim from cutoffs.yaml)",
        "Instrument meta (verbatim from instrument.yaml)",
        "Prompt rendered for this run",
        "Scope-resolved substrate paths",
    }
