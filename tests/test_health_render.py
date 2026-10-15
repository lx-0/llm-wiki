"""M033-S04-T06 — characterisation of `scripts/health.py::render` (the one-shot ASCII vault
dashboard) on a tmp vault with a fixed clock: every box, the counts, the bars, the orphan
line, the compile gate, the latest-file lines, the sparkline, and `main`'s exit codes.
Written before the split. (`tests/test_health.py` is `core/health.py`, the doctor.)"""

from __future__ import annotations

import datetime as dt
import json
import sys
import types

import pytest

import health


@pytest.fixture
def vault(tmp_path, monkeypatch):
    class _Datetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 15, 19, 30)

    class _Date(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 10, 15)

    monkeypatch.setattr(
        health, "dt", types.SimpleNamespace(datetime=_Datetime, date=_Date, timedelta=dt.timedelta)
    )
    monkeypatch.setattr(health, "collect_run_progress", lambda v: (0, 0))
    monkeypatch.setenv("NO_COLOR", "1")

    k = tmp_path / "knowledge"
    for sub, n in (("concepts", 3), ("connections", 1), ("projects", 2)):
        (k / sub).mkdir(parents=True)
        for i in range(n):
            linked = sub == "concepts" and i < 2
            (k / sub / f"{sub}-{i}.md").write_text(
                f"# {sub} {i}\n\n[[a]] and [[b]]\n" if linked else "# plain\n", encoding="utf-8"
            )
    (tmp_path / "raw" / "memories").mkdir(parents=True)
    (tmp_path / "raw" / "memories" / "m.md").write_text("m\n", encoding="utf-8")
    (tmp_path / "raw" / "notes" / "sub").mkdir(parents=True)
    (tmp_path / "raw" / "notes" / "a.md").write_text("a\n", encoding="utf-8")
    (tmp_path / "raw" / "notes" / "sub" / "b.md").write_text("b\n", encoding="utf-8")
    (tmp_path / "daily").mkdir()
    for day in ("2026-10-15", "2026-10-14", "2026-10-10"):
        (tmp_path / "daily" / f"{day}.md").write_text("# day\n", encoding="utf-8")
    state = tmp_path / ".wiki" / "state"
    state.mkdir(parents=True)
    (state / "state.json").write_text(json.dumps({"ingested": {"a": 1, "b": 2}}), encoding="utf-8")
    return tmp_path


def test_render_lays_out_every_box(vault) -> None:
    out = health.render(vault)

    for needle in (
        "║  WIKI HEALTH  ·  2026-10-15 19:30",
        "╭─ KNOWLEDGE ",
        " 6 articles  ╮",
        "concepts     ████████████████████████     3",
        "connections  ████████░░░░░░░░░░░░░░░░     1",
        "projects     ████████████████░░░░░░░░     2",
        "╭─ RAW SOURCES ",
        " 6 total  ╮",
        "memories     ████████░░░░░░░░░░░░░░░░     1  16.7%",
        "notes        ████████████████░░░░░░░░     2  33.3%",
        "articles     ░░░░░░░░░░░░░░░░░░░░░░░░     0   <0.1%",
        "daily        ████████████████████████     3  50.0%",
        "inbox        ░░░░░░░░░░░░░░░░░░░░░░░░     0   <0.1%",
        "Clippings    ░░░░░░░░░░░░░░░░░░░░░░░░     0   <0.1%",
        "╭─ COMPILE BACKLOG ",
        "ingested  █████████░░░░░░░░░░░░░░░░░  33.3%   2/6",
        "backlog: 4 files open",
        "╭─ GRAPH DENSITY ",
        "links/concept  █░░░░░░░░░░░░░░░░░   1.3  target 15-25",
        "orphans        ✕ 1 concepts without [[wikilinks]]",
        "c:cn ratio      3.0 : 1  (3c / 1cn)",
        "╭─ PIPELINE CADENCE ",
        "compile gate     ✓ open  (hour=19≥18)",
        "latest daily     2026-10-15.md",
        "latest review    —",
        "daily activity   ▁▁▁▁▁▁▁▁█▁▁▁██  (last 14d)",
    ):
        assert needle in out, needle
    assert "ACTIVE COMPILE RUN" not in out
    # Every box line is padded to the same width (the frame is intact without colour).
    for ln in out.splitlines():
        if ln.startswith("│"):
            assert len(ln) == 62, ln


def test_render_shows_the_active_run_box_and_the_gated_hour(vault, monkeypatch) -> None:
    monkeypatch.setattr(health, "collect_run_progress", lambda v: (7, 9))
    monkeypatch.setattr(
        health.dt.datetime,
        "now",
        classmethod(lambda cls, tz=None: dt.datetime(2026, 10, 15, 9, 5)),
    )

    out = health.render(vault)

    assert "║  WIKI HEALTH  ·  2026-10-15 09:05" in out
    assert "╭─ ACTIVE COMPILE RUN " in out and " cap=100  ╮" in out
    assert "progress  ██░░░░░░░░░░░░░░░░░░░░░░░░   7.0%   7/100" in out
    assert "compile gate     ● gated (hour=9<18)" in out
    assert "latest daily     2026-10-15.md" in out


def test_render_on_an_empty_vault_is_still_framed(tmp_path, vault, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    out = health.render(empty)

    assert " 0 articles  ╮" in out and " 0 total  ╮" in out
    assert "ingested  ░░░░░░░░░░░░░░░░░░░░░░░░░░   0.0%   0/0" in out
    assert "backlog: 0 files open" in out
    assert "links/concept  ░░░░░░░░░░░░░░░░░░   0.0  target 15-25" in out
    assert "orphans        ✓ 0 concepts without [[wikilinks]]" in out
    assert "c:cn ratio      0.0 : 1  (0c / 0cn)" in out
    assert "latest daily     —" in out and "daily activity" not in out


def test_main_prints_the_dashboard_and_rejects_a_non_vault(
    vault, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "argv", ["health.py", "--vault", str(vault)])
    assert health.main() == 0
    assert "WIKI HEALTH" in capsys.readouterr().out

    stray = tmp_path / "stray"
    stray.mkdir()
    monkeypatch.setattr(sys, "argv", ["health.py", "--vault", str(stray)])
    assert health.main() == 1
    assert "doesn't look like a wiki vault (no knowledge/ or .wiki/)" in capsys.readouterr().err
