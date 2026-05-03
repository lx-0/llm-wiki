"""Tests for hard-fact creation (sources + trust) and prompt rendering."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml


def _patch_facts_dir(monkeypatch: pytest.MonkeyPatch, facts_dir: Path) -> None:
    """Point both correct.py and utils.py at a tmp facts dir."""
    import config
    import correct
    import utils

    facts_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "FACTS_DIR", facts_dir)
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", facts_dir.parent)
    monkeypatch.setattr(correct, "FACTS_DIR", facts_dir)
    monkeypatch.setattr(utils, "FACTS_DIR", facts_dir)
    monkeypatch.setattr(utils, "KNOWLEDGE_DIR", facts_dir.parent)


def _add_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        title="Senkrechtstarter award",
        body="We did NOT win the Senkrechtstarter award.",
        status="negation",
        trust="confirmed",
        source=["https://example.com/proof"],
        term=["senkrechtstarter award"],
        slug=None,
        force=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _read_fact(facts_dir: Path, slug: str) -> dict:
    path = facts_dir / f"{slug}.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    return yaml.safe_load(text[4:end])


# ── correct.cmd_add ─────────────────────────────────────────────────────


def test_add_writes_sources_and_trust(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct

    rc = correct.cmd_add(_add_args(
        source=["https://handelsblatt.de/x", "raw/clippings/mail.md"],
        trust="confirmed",
    ))
    assert rc == 0

    fm = _read_fact(facts_dir, "senkrechtstarter-award")
    assert fm["type"] == "fact"
    assert fm["status"] == "negation"
    assert fm["trust"] == "confirmed"
    assert fm["sources"] == ["https://handelsblatt.de/x", "raw/clippings/mail.md"]
    assert fm["applied"] is False
    assert fm["negation_terms"] == ["senkrechtstarter award"]


def test_add_rejects_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct

    rc = correct.cmd_add(_add_args(source=[]))
    assert rc == 2
    assert not (facts_dir / "senkrechtstarter-award.md").exists()


def test_add_rejects_blank_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct

    rc = correct.cmd_add(_add_args(source=["   ", ""]))
    assert rc == 2


def test_add_user_source_with_default_trust(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct

    rc = correct.cmd_add(_add_args(
        title="Office hours",
        body="Office opens at 10am Monday.",
        status="clarification",
        source=["user:2026-05-03"],
        trust=correct.DEFAULT_TRUST,
        term=[],
    ))
    assert rc == 0

    fm = _read_fact(facts_dir, "office-hours")
    assert fm["trust"] == "asserted"
    assert fm["sources"] == ["user:2026-05-03"]


def test_add_rejects_invalid_trust(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct

    rc = correct.cmd_add(_add_args(trust="bogus"))
    assert rc == 2


# ── utils.read_hard_facts ───────────────────────────────────────────────


def _write_legacy_fact(facts_dir: Path, slug: str, body: str = "Legacy body.") -> None:
    """Write a fact in the pre-trust format (no trust, no sources)."""
    fm = {
        "title": slug,
        "type": "fact",
        "status": "negation",
        "created": "2026-01-01",
        "updated": "2026-01-01",
        "applied": False,
        "negation_terms": [],
    }
    serialized = yaml.safe_dump(fm, sort_keys=False).rstrip()
    facts_dir.mkdir(parents=True, exist_ok=True)
    (facts_dir / f"{slug}.md").write_text(f"---\n{serialized}\n---\n\n{body}\n", encoding="utf-8")


def test_read_hard_facts_sorts_by_trust(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct
    import utils

    correct.cmd_add(_add_args(title="A provisional", body="X", trust="provisional", term=[]))
    correct.cmd_add(_add_args(title="B confirmed", body="Y", trust="confirmed", term=[]))
    correct.cmd_add(_add_args(title="C asserted", body="Z", trust="asserted", term=[]))

    out = utils.read_hard_facts()
    pos_confirmed = out.index("[trust: confirmed]")
    pos_asserted = out.index("[trust: asserted]")
    pos_provisional = out.index("[trust: provisional]")
    assert pos_confirmed < pos_asserted < pos_provisional


def test_read_hard_facts_renders_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import correct
    import utils

    correct.cmd_add(_add_args(
        source=["https://x.test/a", "user:2026-05-03"],
        trust="confirmed",
        term=[],
    ))
    out = utils.read_hard_facts()
    assert "Sources: https://x.test/a, user:2026-05-03" in out
    assert "[trust: confirmed]" in out


def test_read_hard_facts_legacy_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import utils

    _write_legacy_fact(facts_dir, "old-fact")
    out = utils.read_hard_facts()
    assert "[trust: asserted]" in out
    assert "user:legacy-pre-trust-schema" in out


def test_read_hard_facts_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facts_dir = tmp_path / "knowledge" / "facts"
    _patch_facts_dir(monkeypatch, facts_dir)
    import utils

    assert utils.read_hard_facts() == "(no hard facts recorded)"
