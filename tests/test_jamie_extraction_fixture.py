"""M005-S03-T04: smoke test for the synthetic jamie substrate fixture.

Verifies the substrate-path triggers the compile prompt's commitment-
extraction rule and that the rendered prompt carries the substrate
content end-to-end. No LLM call; emission validation is T05's job.
"""
from __future__ import annotations

from pathlib import Path

from core.prompts import render

FIXTURE_REL = "tests/fixtures/jamie/2026-04-15--canary-q1-review--abc.md"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "jamie" / "2026-04-15--canary-q1-review--abc.md"


def test_fixture_exists_with_jamie_naming_convention() -> None:
    assert FIXTURE_PATH.exists(), f"missing fixture: {FIXTURE_PATH}"
    # `<date>--<slug>--<short-id>.md` per the collector convention
    name = FIXTURE_PATH.name
    parts = name.removesuffix(".md").split("--")
    assert len(parts) == 3, f"jamie filename must have 3 `--`-separated parts: {name}"
    date_part, slug, short_id = parts
    assert len(date_part) == 10 and date_part.count("-") == 2, "date part must be YYYY-MM-DD"


def test_fixture_carries_canonical_commitment_markers() -> None:
    body = FIXTURE_PATH.read_text(encoding="utf-8")
    # Three commitment signals the LLM rule should catch:
    assert "I'll send the Q3 deck by next Friday" in body
    assert "EOD April 22nd" in body
    assert "I'll set up the Bob intro" in body
    assert "waiting on the infra-capacity decision from Hetzner" in body
    # Anti-extraction control (hypothetical rejected):
    assert "Hypothetically" in body


def test_rendered_prompt_carries_substrate_and_extraction_rule() -> None:
    body = FIXTURE_PATH.read_text(encoding="utf-8")
    rendered = render(
        "compile_main",
        agents_md="",
        facts_md="",
        index_md="",
        owner_block="",
        source_path="raw/transcripts/jamie/2026-04-15--canary-q1-review--abc.md",
        source_content=body,
        today="2026-04-15",
        now="2026-04-15T10:00:00Z",
    )
    # Extraction rule reaches the prompt
    assert "Extracting commitments from meeting + voice substrates" in rendered
    # The substrate body is interpolated unchanged (substring check)
    assert "I'll send the Q3 deck by next Friday" in rendered
    assert "waiting on the infra-capacity decision from Hetzner" in rendered
    # Substrate-path is passed to the prompt
    assert "raw/transcripts/jamie/2026-04-15--canary-q1-review--abc.md" in rendered
