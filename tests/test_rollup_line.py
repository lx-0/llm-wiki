"""M033-S03-T06 — one timed rollup line, one ellipsis, one swallowed append.

`core.utils.ellipsize` is the 80/77 rule's one home; `daily_capture.rollup_line` builds the
`- **HH:MM** · …` line every inbox collector mirrors into `daily/<date>/<source>.md`; the
per-collector shapes are pinned byte-for-byte from the pre-fold parity capture
(`/tmp/t06-parity-before.txt`, 2026-10-15); two guards keep the next copy out.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core import daily_capture
from core.utils import ellipsize

REPO = Path(__file__).resolve().parent.parent
AT = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo("Europe/Berlin"))
LONG = "word " * 30  # 150 chars → cut at 77 + "…"
LONG_CUT = "word word word word word word word word word word word word word word word wo…"


@pytest.fixture
def daily(tmp_path, monkeypatch) -> Path:
    """Pin DAILY_DIR to tmp_path/daily so the collectors' rollup never touches a vault."""
    d = tmp_path / "daily"
    monkeypatch.setattr(daily_capture, "DAILY_DIR", d)
    return d


# ── ellipsize ────────────────────────────────────────────────────────


def test_ellipsize_keeps_text_within_limit():
    assert ellipsize("short") == "short"
    assert ellipsize("x" * 80) == "x" * 80


def test_ellipsize_cuts_at_limit_minus_three_and_strips_before_the_mark():
    assert ellipsize(LONG) == LONG_CUT
    assert len(ellipsize(LONG)) == 78
    assert ellipsize("abcdefghij", limit=8) == "abcde…"


# ── rollup_line ──────────────────────────────────────────────────────


def test_rollup_line_stamps_date_and_time_and_takes_the_first_line():
    date_iso, line = daily_capture.rollup_line(AT, "Hello from the dictation.\nsecond line")
    assert date_iso == "2026-01-02"
    assert line == "- **09:30** · Hello from the dictation."


def test_rollup_line_empty_text_uses_the_placeholder():
    assert daily_capture.rollup_line(AT, "")[1] == "- **09:30** · (empty)"
    assert (
        daily_capture.rollup_line(AT, "", empty="(no description)")[1]
        == "- **09:30** · (no description)"
    )


def test_rollup_line_prefix_suffix_and_ellipsis():
    _, line = daily_capture.rollup_line(AT, LONG, prefix="`id` · ", suffix=" → [[x]]")
    assert line == f"- **09:30** · `id` · {LONG_CUT} → [[x]]"


# ── the collectors' shapes, byte-for-byte from the parity capture ────


def test_capture_rollup_shape(daily):
    from collectors import capture_collector

    capture_collector._append_daily_rollup(
        "abc12345",
        AT,
        "A thought worth a rollup line\nmore",
        Path("/v/raw/captures/capture-abc12345.md"),
    )
    capture_collector._append_daily_rollup(
        "ffff0000", AT, LONG, Path("/v/raw/captures/capture-ffff0000.md")
    )
    capture_collector._append_daily_rollup(
        "00000000", AT, "", Path("/v/raw/captures/capture-00000000.md")
    )
    assert (daily / "2026-01-02" / "captures.md").read_text(encoding="utf-8") == (
        "- **09:30** · `abc12345` · A thought worth a rollup line → [[capture-abc12345]]\n"
        f"- **09:30** · `ffff0000` · {LONG_CUT} → [[capture-ffff0000]]\n"
        "- **09:30** · `00000000` · (empty) → [[capture-00000000]]\n"
    )


def test_pictures_rollup_shape(daily):
    from collectors import pictures

    pictures._append_daily_rollup(AT, "A scene with a cat", "IMG_0001.jpg")
    pictures._append_daily_rollup(AT, "", "IMG_0002.jpg")
    pictures._append_daily_rollup(AT, LONG, "IMG_0003.jpg")
    assert (daily / "2026-01-02" / "pictures.md").read_text(encoding="utf-8") == (
        "- **09:30** · A scene with a cat · `IMG_0001.jpg`\n"
        "- **09:30** · (no description) · `IMG_0002.jpg`\n"
        f"- **09:30** · {LONG_CUT} · `IMG_0003.jpg`\n"
    )


def test_voice_rollup_shape_with_sources_frontmatter(daily):
    from collectors import voice

    voice._append_daily_rollup(
        AT,
        "Hello from the dictation.\nsecond line",
        Path("/v/raw/voice/voice-2026-01-02-0930-hello.md"),
    )
    voice._append_daily_rollup(AT, LONG, Path("/v/raw/voice/voice-2026-01-02-0930-long.md"))
    voice._append_daily_rollup(AT, "", Path("/v/raw/voice/voice-2026-01-02-0930-empty.md"))
    assert (daily / "2026-01-02" / "voice.md").read_text(encoding="utf-8") == (
        "---\n"
        "sources:\n"
        "  - voice-2026-01-02-0930-hello.md\n"
        "  - voice-2026-01-02-0930-long.md\n"
        "  - voice-2026-01-02-0930-empty.md\n"
        "---\n"
        "- **09:30** · Hello from the dictation.\n"
        f"- **09:30** · {LONG_CUT}\n"
        "- **09:30** · (empty)\n"
    )


# ── guards ───────────────────────────────────────────────────────────

_DIRECT_APPEND = re.compile(r"daily_capture\.(append|append_with_source)\(")


def test_collectors_append_rollups_only_through_the_harness():
    """`base.append_rollup` is the one swallowed-failure append — a collector that calls
    `daily_capture.append` itself re-types the try/except that the harness owns (jamie,
    gmeet, health ×2, email did)."""
    offenders = [
        f"{p.relative_to(REPO)}:{n}"
        for p in sorted((REPO / "scripts" / "collectors").rglob("*.py"))
        if p.name != "base.py"
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _DIRECT_APPEND.search(line)
    ]
    assert offenders == [], "daily_capture.append outside base.append_rollup:\n" + "\n".join(
        offenders
    )


def test_the_ellipsis_rule_has_one_home():
    """`[:77]` is the 80-char cut spelled by hand — five copies before the fold."""
    offenders = [
        f"{p.relative_to(REPO)}:{n}"
        for p in sorted((REPO / "scripts").rglob("*.py"))
        if p != REPO / "scripts" / "core" / "utils.py"
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "[:77]" in line
    ]
    assert offenders == [], "hand-spelled ellipsis outside core.utils.ellipsize:\n" + "\n".join(
        offenders
    )
