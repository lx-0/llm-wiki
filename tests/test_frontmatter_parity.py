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
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

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


# ── no private grammar outside the seam (M033-S03-T02) ───────────────────────

_SEAM = REPO / "scripts" / "core" / "frontmatter.py"
# What a hand-rolled READ grammar looks like: its own YAML load, a fence regex, or a
# fence probe on the text. Emitting a `---` line (the writers in voice / capture / inbox
# build their own YAML shape on purpose) is not parsing and is not flagged.
_GRAMMAR_SMELLS = (
    "yaml.safe_load",
    "\\A---",
    "^---",
    'startswith("---',
    "startswith('---",
    'find("\\n---',
    'index("\\n---',
)
_FRONTMATTER_DEF = re.compile(
    r"^def ([A-Za-z_]*frontmatter[A-Za-z_]*)\(.*?(?=^(?:def |class |[A-Z_][A-Z0-9_]* = )|\Z)",
    re.MULTILINE | re.DOTALL,
)


def test_no_private_frontmatter_grammar_outside_the_seam() -> None:
    """`core/frontmatter.py` is the one grammar. Any other top-level function named after
    frontmatter may wrap the seam (read a file, keep a `None` / exception contract) or
    build a block to write, but may not read a fence with a grammar of its own."""
    offenders: list[str] = []
    for path in sorted((REPO / "scripts").rglob("*.py")):
        if path == _SEAM:
            continue
        text = path.read_text(encoding="utf-8")
        for m in _FRONTMATTER_DEF.finditer(text):
            smells = [s for s in _GRAMMAR_SMELLS if s in m.group(0)]
            if smells:
                offenders.append(f"{path.relative_to(REPO)}:{m.group(1)} {smells}")
    assert offenders == [], (
        "private frontmatter grammar outside core/frontmatter.py:\n" + "\n".join(offenders)
    )


# ── no fence grammar ANYWHERE outside the seam (M033-S03-T07) ────────────────

# A hand-rolled fence READ at line level: a fence regex, a `startswith` / `find` probe on
# the text, or one of the private regex names the unnamed sites carried. Writers that emit
# a `---` line are not matched (no `"---\n"` in the list).
_FENCE_READ_SMELLS = (
    "\\A---",
    '"^---',
    'startswith("---',
    "startswith('---",
    'find("\\n---',
    'index("\\n---',
    "_FM_RE",
    "_FRONTMATTER_RE",
)
# Lines that look like a fence read and are not — the reason stands beside each.
_ALLOWED_FENCE_LINES = {
    "scripts/lint.py": (
        "`^---\\s*$` over the BODY finds thematic breaks before `## Timeline`, not a fence"
    ),
}


def test_no_fence_grammar_anywhere_outside_the_seam() -> None:
    """Exit criterion 5 at line level: T02's guard looked only inside `*frontmatter*`-named
    functions and missed eight grammars under other names (T03's smell grep found them —
    health's merge read, two calendar probes, capture_index, daily_capture, the word count,
    the final-only probe, the type migration, the suggestion loader). Every line of every
    module under scripts/ is scanned; the one `---` scan that is not a fence is allow-listed
    with its reason."""
    offenders: list[str] = []
    for path in sorted((REPO / "scripts").rglob("*.py")):
        rel = str(path.relative_to(REPO))
        if path == _SEAM or rel in _ALLOWED_FENCE_LINES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            smells = [s for s in _FENCE_READ_SMELLS if s in line]
            if smells:
                offenders.append(f"{rel}:{n} {smells}")
    assert offenders == [], "fence grammar outside core/frontmatter.py:\n" + "\n".join(offenders)
