"""Tests for the runner's report writer (`_persist_report`).

Pins the frontmatter the deepened runner emits — loader-surfaced likert /
max_total / concern_bands — and the per-batch prompt embedding that fixed
the prompt-divergence bug (the embedded prompts are the ACTUAL hashed
prompts, not a divergent second render).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.reports._engine.instrument import load_instrument
from scripts.reports._engine.lib.inference import InferenceRun
from scripts.reports._engine.lib.timeline import _snapshot_from_report
from scripts.reports._engine.runner import _persist_report
from scripts.reports._engine.score import score_instrument


_INSTRUMENTS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "reports" / "_engine" / "instruments"
)


def _phq9():
    return load_instrument(_INSTRUMENTS_ROOT / "phq-9" / "v1.0.0")


def _split_frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    fm_end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:fm_end])


def test_frontmatter_carries_loader_surfaced_geometry(tmp_path: Path) -> None:
    instr = _phq9()
    scored = score_instrument(instr.instrument_path, {})
    run = InferenceRun(instrument_slug="phq-9", instrument_version="1.0.0")

    report = _persist_report(
        output_dir=tmp_path,
        timestamp="2026-05-17T10-00-00",
        instrument=instr,
        scored=scored,
        run=run,
        rendered_batches=[("all", "abc1234567890def", "RENDERED PROMPT BODY")],
        prompt_version="abc1234567890def",
        lookback_days=14,
        substrate_paths=[],
        vault_root=tmp_path,
    )
    text = report.read_text(encoding="utf-8")
    fm = _split_frontmatter(text)

    assert fm["likert"] == {"lo": 0, "hi": 3}
    assert fm["max_total"] == 27
    assert fm["concern_bands"] == ["moderate", "moderately-severe", "severe"]
    # Score line reflects the surfaced max.
    assert "0 / 27" in text


def test_embeds_actual_per_batch_prompt(tmp_path: Path) -> None:
    instr = _phq9()
    scored = score_instrument(instr.instrument_path, {})
    run = InferenceRun(instrument_slug="phq-9", instrument_version="1.0.0")

    report = _persist_report(
        output_dir=tmp_path,
        timestamp="2026-05-17T10-00-00",
        instrument=instr,
        scored=scored,
        run=run,
        rendered_batches=[
            ("part-a", "1111aaaa", "PROMPT ALPHA"),
            ("part-b", "2222bbbb", "PROMPT BETA"),
        ],
        prompt_version="1111aaaa",
        lookback_days=14,
        substrate_paths=[],
        vault_root=tmp_path,
    )
    text = report.read_text(encoding="utf-8")
    # Each batch's real prompt + its version is embedded (no divergent render).
    assert "Batch `part-a`" in text and "prompt_version `1111aaaa`" in text
    assert "PROMPT ALPHA" in text
    assert "Batch `part-b`" in text and "prompt_version `2222bbbb`" in text
    assert "PROMPT BETA" in text
    # The verify_report contract keeps its summary label.
    assert "<summary>Prompt rendered for this run" in text


def test_no_batches_notes_no_sdk_call(tmp_path: Path) -> None:
    instr = _phq9()
    scored = score_instrument(instr.instrument_path, {})
    run = InferenceRun(instrument_slug="phq-9", instrument_version="1.0.0")

    report = _persist_report(
        output_dir=tmp_path,
        timestamp="2026-05-17T10-00-00",
        instrument=instr,
        scored=scored,
        run=run,
        rendered_batches=[],  # every item operator-answered → no SDK call
        prompt_version="",
        lookback_days=14,
        substrate_paths=[],
        vault_root=tmp_path,
    )
    text = report.read_text(encoding="utf-8")
    assert "no SDK call this run" in text


def test_report_round_trips_through_timeline(tmp_path: Path) -> None:
    instr = _phq9()
    scored = score_instrument(instr.instrument_path, {})
    run = InferenceRun(instrument_slug="phq-9", instrument_version="1.0.0")

    report = _persist_report(
        output_dir=tmp_path,
        timestamp="2026-05-17T10-00-00",
        instrument=instr,
        scored=scored,
        run=run,
        rendered_batches=[("all", "abc", "P")],
        prompt_version="abc",
        lookback_days=14,
        substrate_paths=[],
        vault_root=tmp_path,
    )
    snap = _snapshot_from_report(report)
    assert snap is not None
    assert snap.max_total == 27
    assert snap.likert_hi == 3
    assert snap.concern_bands == ("moderate", "moderately-severe", "severe")
