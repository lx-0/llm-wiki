"""Tests for the takes substrate (M011 — third-party belief attribution).

Covers:
- TAKES_DIR / canonical-enumeration / FOLDER_TO_TYPE wiring
- slug normalisation
- first-touch file creation has the expected frontmatter shape
- idempotent add (refuse exact duplicate)
- list / show / remove
- lint check_takes_consistency: shape-only (valid pass / malformed fail /
  frontmatter-missing fail)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml


# ── Wiring ───────────────────────────────────────────────────────────


def test_takes_dir_declared_and_under_knowledge() -> None:
    from core import paths
    assert hasattr(paths, "TAKES_DIR"), "core.paths.TAKES_DIR must exist"
    assert paths.TAKES_DIR == paths.KNOWLEDGE_DIR / "takes"


def test_canonical_enumeration_includes_takes(tmp_path: Path) -> None:
    from core import utils
    # Canonical enumeration (C04): list_wiki_articles walks knowledge/
    # recursively, so takes/ files are corpus members.
    knowledge = tmp_path / "knowledge"
    (knowledge / "takes").mkdir(parents=True)
    md = knowledge / "takes" / "jane.md"
    md.write_text("---\ntype: takes\nholder: jane\n---\n", encoding="utf-8")
    assert md in utils.list_wiki_articles(knowledge)


def test_lint_folder_to_type_maps_takes() -> None:
    import lint
    assert lint.FOLDER_TO_TYPE.get("takes") == "takes"


# ── take CLI ─────────────────────────────────────────────────────────


def _patch_takes_dir(monkeypatch: pytest.MonkeyPatch, takes_dir: Path) -> None:
    """Point both take.py and lint.py at a tmp takes dir.

    Mirrors `_patch_facts_dir` in test_correct.py — every consumer module
    binds its own `from core.paths import …` name, so monkeypatch must
    hit each.
    """
    from facts import take
    from core import paths

    takes_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(take, "TAKES_DIR", takes_dir)
    monkeypatch.setattr(paths, "TAKES_DIR", takes_dir)
    monkeypatch.setattr(paths, "KNOWLEDGE_DIR", takes_dir.parent)


def _add_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        holder="Jane Doe",
        belief="GPT-5 commoditizes agent platforms within 12 months.",
        confidence="high",
        source="raw/transcripts/jamie/2026-04-15--abc.md",
        date=None,
        slug=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _read_takes_file(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "must start with YAML frontmatter"
    end = text.find("\n---\n", 4)
    assert end != -1
    fm = yaml.safe_load(text[4:end])
    body = text[end + 5 :]
    return fm, body


def test_slug_normalisation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Holder name slugifies to kebab-case filename."""
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc = take.cmd_add(_add_args(holder="Jane Doe"))
    assert rc == 0
    assert (takes_dir / "jane-doe.md").exists()

    rc = take.cmd_add(_add_args(
        holder="José García-López",
        belief="A different belief.",
        source="daily/2026-05-15.md",
    ))
    assert rc == 0
    # slugify drops accents to plain ASCII via the existing core.utils.slugify
    # (lowercase + non-word chars → hyphens). The exact mapping depends on
    # slugify's handling of unicode — assert the produced filename is what
    # slugify returned for this input.
    from core.utils import slugify
    expected = slugify("José García-López")
    assert (takes_dir / f"{expected}.md").exists()


def test_first_touch_frontmatter_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc = take.cmd_add(_add_args())
    assert rc == 0
    fm, body = _read_takes_file(takes_dir / "jane-doe.md")
    assert fm["type"] == "takes"
    assert fm["holder"] == "jane-doe"
    assert fm["title"] == "Takes — Jane Doe"
    assert "created" in fm and "last_updated" in fm
    assert "# Takes — Jane Doe" in body
    # Body contains exactly one take line matching the canonical shape.
    lines = [l for l in body.splitlines() if l.startswith("- **")]
    assert len(lines) == 1
    assert "[high]" in lines[0]
    assert "raw/transcripts/jamie/2026-04-15--abc.md" in lines[0]


def test_idempotent_add_refuses_exact_duplicate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    fixed_date = "2026-04-15"
    args = _add_args(date=fixed_date)
    rc1 = take.cmd_add(args)
    assert rc1 == 0
    # Same date + confidence + source + belief = exact duplicate; must be no-op.
    rc2 = take.cmd_add(args)
    assert rc2 == 0

    fm, body = _read_takes_file(takes_dir / "jane-doe.md")
    take_lines = [l for l in body.splitlines() if l.startswith("- **")]
    assert len(take_lines) == 1, f"expected idempotent add, got {take_lines}"


def test_add_appends_distinct_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc1 = take.cmd_add(_add_args(date="2026-04-15", belief="First take."))
    rc2 = take.cmd_add(_add_args(date="2026-04-16", belief="Second take."))
    assert rc1 == 0 and rc2 == 0
    fm, body = _read_takes_file(takes_dir / "jane-doe.md")
    take_lines = [l for l in body.splitlines() if l.startswith("- **")]
    assert len(take_lines) == 2


def test_list_show_remove(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    take.cmd_add(_add_args(date="2026-04-15", belief="Belief one."))
    take.cmd_add(_add_args(date="2026-04-16", belief="Belief two."))
    take.cmd_add(_add_args(
        holder="Bob Smith",
        belief="Bob has a position.",
        date="2026-04-17",
        source="daily/2026-04-17.md",
        confidence="medium",
    ))

    # list
    capsys.readouterr()  # clear
    rc = take.cmd_list(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "jane-doe" in out and "bob-smith" in out
    assert "2 take(s)" in out  # jane has two

    # show
    rc = take.cmd_show(argparse.Namespace(slug="jane-doe"))
    assert rc == 0
    show_out = capsys.readouterr().out
    assert "Belief one." in show_out and "Belief two." in show_out
    assert "1." in show_out and "2." in show_out

    # remove --line 1 (drops the first take line)
    rc = take.cmd_remove(argparse.Namespace(slug="jane-doe", line=1, all=False))
    assert rc == 0
    fm, body = _read_takes_file(takes_dir / "jane-doe.md")
    remaining = [l for l in body.splitlines() if l.startswith("- **")]
    assert len(remaining) == 1
    assert "Belief two." in remaining[0]

    # remove --all
    rc = take.cmd_remove(argparse.Namespace(slug="bob-smith", line=None, all=True))
    assert rc == 0
    assert not (takes_dir / "bob-smith.md").exists()


def test_show_missing_holder_returns_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc = take.cmd_show(argparse.Namespace(slug="nobody"))
    assert rc == 1


def test_remove_requires_line_or_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    take.cmd_add(_add_args())
    rc = take.cmd_remove(argparse.Namespace(slug="jane-doe", line=None, all=False))
    assert rc == 2


def test_add_rejects_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc = take.cmd_add(_add_args(source=""))
    assert rc == 2


def test_add_belief_gets_trailing_period(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    takes_dir = tmp_path / "knowledge" / "takes"
    _patch_takes_dir(monkeypatch, takes_dir)
    from facts import take

    rc = take.cmd_add(_add_args(belief="No terminal punctuation here"))
    assert rc == 0
    fm, body = _read_takes_file(takes_dir / "jane-doe.md")
    line = next(l for l in body.splitlines() if l.startswith("- **"))
    assert line.rstrip().endswith(".")


# ── lint.check_takes_consistency ─────────────────────────────────────


def _ctx(knowledge_dir: Path):
    """LintContext over a fake knowledge/ root."""
    import lint

    return lint.build_context(
        vault=knowledge_dir.parent, knowledge_dir=knowledge_dir, state={}
    )


def test_lint_takes_clean_when_dir_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import lint
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir(parents=True)
    assert lint.check_takes_consistency(_ctx(knowledge)) == []


def test_lint_takes_passes_canonical_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import lint
    knowledge = tmp_path / "knowledge"
    takes = knowledge / "takes"
    takes.mkdir(parents=True)
    (takes / "jane-doe.md").write_text(
        "---\n"
        "title: \"Takes — Jane Doe\"\n"
        "type: takes\n"
        "holder: jane-doe\n"
        "created: 2026-05-13\n"
        "last_updated: 2026-05-13\n"
        "---\n\n"
        "# Takes — Jane Doe\n\n"
        "- **2026-04-15** [high] · `raw/transcripts/jamie/2026-04-15--abc.md` — A clear belief.\n"
        "- **2026-04-16** [medium] · `daily/2026-04-16.md` — Another belief.\n",
        encoding="utf-8",
    )
    assert lint.check_takes_consistency(_ctx(knowledge)) == []


def test_lint_takes_flags_missing_type(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import lint
    knowledge = tmp_path / "knowledge"
    takes = knowledge / "takes"
    takes.mkdir(parents=True)
    (takes / "broken.md").write_text(
        "---\n"
        "holder: broken\n"
        "---\n\n"
        "- **2026-04-15** [high] · `daily/x.md` — Body content.\n",
        encoding="utf-8",
    )
    issues = lint.check_takes_consistency(_ctx(knowledge))
    checks = {i.check for i in issues}
    assert "takes_frontmatter_type" in checks


def test_lint_takes_flags_missing_holder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import lint
    knowledge = tmp_path / "knowledge"
    takes = knowledge / "takes"
    takes.mkdir(parents=True)
    (takes / "no-holder.md").write_text(
        "---\n"
        "type: takes\n"
        "---\n\n"
        "- **2026-04-15** [high] · `daily/x.md` — Body content.\n",
        encoding="utf-8",
    )
    issues = lint.check_takes_consistency(_ctx(knowledge))
    checks = {i.check for i in issues}
    assert "takes_frontmatter_holder_missing" in checks


def test_lint_takes_flags_malformed_line(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import lint
    knowledge = tmp_path / "knowledge"
    takes = knowledge / "takes"
    takes.mkdir(parents=True)
    (takes / "jane-doe.md").write_text(
        "---\n"
        "type: takes\n"
        "holder: jane-doe\n"
        "---\n\n"
        "- **2026-04-15** [high] · `daily/x.md` — Good line.\n"
        "- **2026-04-16** garbage missing fields\n"
        "- **bad-date** [low] · `daily/x.md` — Bad date.\n",
        encoding="utf-8",
    )
    issues = lint.check_takes_consistency(_ctx(knowledge))
    malformed = [i for i in issues if i.check == "takes_line_malformed"]
    assert len(malformed) == 2
    assert all(i.severity == "warning" for i in malformed)


def test_lint_takes_ignores_non_take_bullets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bullets that don't start with `- **` (e.g. plain list intro) are skipped."""
    import lint
    knowledge = tmp_path / "knowledge"
    takes = knowledge / "takes"
    takes.mkdir(parents=True)
    (takes / "jane-doe.md").write_text(
        "---\n"
        "type: takes\n"
        "holder: jane-doe\n"
        "---\n\n"
        "# Takes — Jane Doe\n\n"
        "- a plain list bullet (not a take)\n"
        "- **2026-04-15** [high] · `daily/x.md` — Real take.\n",
        encoding="utf-8",
    )
    assert lint.check_takes_consistency(_ctx(knowledge)) == []
