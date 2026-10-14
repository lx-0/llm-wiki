"""The top-level scripts read frontmatter through `core.frontmatter` (M033-S03-T01).

Before this task nine scripts carried their own fence grammar. Each site keeps its
call-site semantics; what changed is the tolerance the seam brings — CRLF files, a closing
fence at EOF without a newline, trailing whitespace on a fence line, YAML quoting and
`# comment` rules — which the private copies refused or misread. The parity run of the
shape table through every old helper (M033-S03-T01 summary) showed exactly those classes
of difference and nothing else; these tests pin the seam's answer at each site so the
behaviour cannot drift back, plus the two call-site contracts that were kept on purpose.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

CRLF_PERSON = (
    "---\r\ntitle: Sam Rivera\r\ntype: person\r\naliases: [Sam, S. Rivera]\r\n---\r\n"
    "\r\n# Sam\r\n\r\nBody.\r\n"
)


# ── pin: type + compile_role ─────────────────────────────────────────────────


def test_pin_reads_type_and_compile_role_through_the_seam(tmp_path: Path) -> None:
    import pin

    article = tmp_path / "x.md"
    article.write_bytes(
        b"---\r\ntype: concept  # trailing note\r\ncompile_role: final-only\r\n---\r\nBody\r\n"
    )
    fm = pin._read_frontmatter(article)
    assert fm.get("type") == "concept"  # the YAML comment is not part of the value
    assert fm.get("compile_role") == "final-only"


# ── cleanup_legacy_daily_roots: the digest predicate ─────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\ntype: daily-digest\n---\nBody\n", True),
        ('---\ntype: "daily-digest"\n---\nBody\n', True),  # quotes are YAML, not the value
        ("---\r\ntype: daily-digest\r\n---\r\nBody\r\n", True),
        ("---\ntype: daily-digest-extra\n---\nBody\n", False),  # exact match, no prefix
        ("---\ntitle: no type\n---\nBody\n", False),
        ("# no frontmatter\n", False),
    ],
)
def test_cleanup_digest_detection(text: str, expected: bool) -> None:
    import cleanup_legacy_daily_roots as cleanup

    assert cleanup._has_digest_frontmatter(text) is expected


# ── backfill_daily_rollup: title + body through the seam ─────────────────────


def test_rollup_meetings_title_from_crlf_frontmatter(tmp_path: Path) -> None:
    import backfill_daily_rollup as roll

    jamie = tmp_path / "raw" / "transcripts" / "jamie"
    jamie.mkdir(parents=True)
    (jamie / "2026-01-02--quarterly-review--abc123.md").write_bytes(
        b"---\r\ntitle: 'Quarterly Review'\r\n---\r\n\r\nTranscript.\r\n"
    )
    lines = roll._meetings_lines(tmp_path)
    assert lines == [
        ("2026-01-02", "- **jamie** · Quarterly Review → [[2026-01-02--quarterly-review--abc123]]")
    ]


def test_rollup_voice_first_line_skips_crlf_frontmatter(tmp_path: Path) -> None:
    import backfill_daily_rollup as roll

    voice = tmp_path / "raw" / "voice"
    voice.mkdir(parents=True)
    (voice / "voice-2026-01-02-0930-note.md").write_bytes(
        b"---\r\nsource: voice\r\n---\r\n\r\nHello from the dictation.\r\n"
    )
    lines = roll._voice_lines(tmp_path)
    assert lines == [
        ("2026-01-02", "- **09:30** · Hello from the dictation. → [[voice-2026-01-02-0930-note]]")
    ]


def test_rollup_read_frontmatter_keeps_its_warning_contract(tmp_path: Path, caplog) -> None:
    """A malformed file still logs the path and yields {} (tests/test_errors.py pins the
    same thing from the errors side); a fence at EOF now parses."""
    import backfill_daily_rollup as roll

    bad = tmp_path / "bad.md"
    bad.write_text("---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="backfill_daily_rollup"):
        assert roll._read_frontmatter(bad) == {}
    assert any(str(bad) in r.getMessage() for r in caplog.records)

    eof = tmp_path / "eof.md"
    eof.write_text("---\nsleep_hours: 7.5\n---", encoding="utf-8")
    assert roll._read_frontmatter(eof) == {"sleep_hours": 7.5}


# ── backfill_picture_metadata: the None contract ─────────────────────────────


def test_picture_backfill_still_skips_a_malformed_sidecar(tmp_path: Path) -> None:
    import backfill_picture_metadata as pic

    sidecar = tmp_path / "IMG_0001.md"
    sidecar.write_text("---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    assert pic._backfill_one(sidecar, dry_run=True) == "skipped:no_frontmatter"
    sidecar.write_text("# no frontmatter at all\n", encoding="utf-8")
    assert pic._backfill_one(sidecar, dry_run=True) == "skipped:no_frontmatter"


# ── reconcile: cooldown stamp ────────────────────────────────────────────────


def test_reconcile_cooldown_reads_a_fence_at_eof(tmp_path: Path, monkeypatch) -> None:
    import reconcile

    monkeypatch.setattr(reconcile, "FACTS_DIR", tmp_path)
    (tmp_path / "office-hours.md").write_text(
        "---\nlast_reconciled: '2026-10-14T00:00:00+00:00'\n---", encoding="utf-8"
    )
    assert reconcile._within_cooldown("office-hours", cooldown_days=36500) is True
    assert reconcile._within_cooldown("missing", cooldown_days=36500) is False


# ── health_trends: metrics from a CRLF rollup ────────────────────────────────


def test_health_metrics_collected_from_a_crlf_rollup(tmp_path: Path) -> None:
    import health_trends as ht

    (tmp_path / "2026-02-02--default.md").write_bytes(
        b"---\r\ntitle: Health\r\ntype: health-rollup\r\ndate: '2026-02-02'\r\nsteps: 2000\r\n---\r\n\r\n# Health\r\n"
    )
    series, days, span = ht.collect_metrics(tmp_path)
    assert days == 1
    assert span == ("2026-02-02", "2026-02-02")
    assert series["steps"] == [("2026-02-02", 2000.0)]


# ── dedup: entity page ───────────────────────────────────────────────────────


def test_dedup_load_entity_reads_a_crlf_page(tmp_path: Path) -> None:
    import dedup

    page = tmp_path / "sam-rivera.md"
    page.write_bytes(CRLF_PERSON.encode("utf-8"))
    ent = dedup.load_entity(page, "people")
    assert ent.title == "Sam Rivera"
    assert ent.aliases == ["Sam", "S. Rivera"]
