"""Tests for the optional `domain:` frontmatter axis (M013).

Spec: `.ytstack/backlog/domain-frontmatter.md`.

Covers:
- CONFIG.personal.domains default = ["company", "personal", "ai", "meta"]
- migrate_config_keys KEY_ADDITIONS["personal"]["domains"] injects the same default
- migrate_additions actually inserts personal.domains into a config missing it
- lint.check_domain_value passes on a valid value, warns on an unknown one,
  ignores articles that omit `domain:`, and no-ops when CONFIG.personal.domains
  is empty
- query.py argparse accepts --domain <value>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


# ── 1. config default ───────────────────────────────────────────────────


def test_config_personal_domains_default() -> None:
    """Dataclass default ships the enum lifted from the lx-vault audit."""
    from core.config import CONFIG
    assert CONFIG.personal.domains == ["company", "personal", "ai", "meta"]


# ── 2. migration: KEY_ADDITIONS entry + apply ───────────────────────────


def test_migrate_key_additions_has_domains() -> None:
    from migrations import migrate_config_keys as m
    assert "personal" in m.KEY_ADDITIONS
    assert m.KEY_ADDITIONS["personal"]["domains"] == [
        "company", "personal", "ai", "meta",
    ]


def test_migrate_additions_injects_domains_into_personal_block() -> None:
    """A config missing personal.domains gets it injected with the default."""
    from migrations import migrate_config_keys as m
    data: dict = {"personal": {"primary_account": "alex"}}
    changes = m.migrate_additions(data)
    assert data["personal"]["domains"] == ["company", "personal", "ai", "meta"]
    assert any("personal.domains" in c for c in changes), changes


def test_migrate_additions_idempotent_when_present() -> None:
    """A config that already pins personal.domains keeps the operator value."""
    from migrations import migrate_config_keys as m
    data: dict = {"personal": {"domains": ["work", "home"]}}
    changes = m.migrate_additions(data)
    assert data["personal"]["domains"] == ["work", "home"]
    assert not any("personal.domains" in c for c in changes)


# ── 3. lint check_domain_value ──────────────────────────────────────────


def _seed_article(tmp_path: Path, name: str, domain: str | None) -> Path:
    art = tmp_path / "knowledge" / "concepts" / name
    art.parent.mkdir(parents=True, exist_ok=True)
    if domain is None:
        art.write_text("---\ntype: concept\ntags: [llm-wiki]\n---\n# x\n", encoding="utf-8")
    else:
        art.write_text(
            f"---\ntype: concept\ntags: [llm-wiki]\ndomain: {domain}\n---\n# x\n",
            encoding="utf-8",
        )
    return art


def test_check_domain_value_passes_on_valid(tmp_path, monkeypatch) -> None:
    import lint

    fake_knowledge = tmp_path / "knowledge"
    fake_knowledge.mkdir(parents=True)
    _seed_article(tmp_path, "good.md", "company")

    # Force config to a deterministic enum for the check.
    monkeypatch.setattr(
        lint.CONFIG.personal, "domains", ["company", "personal", "ai", "meta"]
    )

    ctx = lint.build_context(vault=tmp_path, knowledge_dir=fake_knowledge, state={})
    issues = lint.check_domain_value(ctx)
    assert issues == [], f"valid value must produce no issues, got {issues}"


def test_check_domain_value_warns_on_unknown(tmp_path, monkeypatch) -> None:
    import lint

    fake_knowledge = tmp_path / "knowledge"
    fake_knowledge.mkdir(parents=True)
    _seed_article(tmp_path, "bad.md", "fintech")

    monkeypatch.setattr(
        lint.CONFIG.personal, "domains", ["company", "personal", "ai", "meta"]
    )

    ctx = lint.build_context(vault=tmp_path, knowledge_dir=fake_knowledge, state={})
    issues = lint.check_domain_value(ctx)
    assert len(issues) == 1, issues
    assert issues[0].check == "domain_invalid_value"
    assert issues[0].severity == "warning"
    assert "fintech" in issues[0].detail


def test_check_domain_value_ignores_untagged(tmp_path, monkeypatch) -> None:
    """Articles without `domain:` are silently in-scope — the feature is opt-in."""
    import lint

    fake_knowledge = tmp_path / "knowledge"
    fake_knowledge.mkdir(parents=True)
    _seed_article(tmp_path, "untagged.md", None)

    monkeypatch.setattr(
        lint.CONFIG.personal, "domains", ["company", "personal", "ai", "meta"]
    )

    ctx = lint.build_context(vault=tmp_path, knowledge_dir=fake_knowledge, state={})
    assert lint.check_domain_value(ctx) == []


def test_check_domain_value_noop_when_enum_empty(tmp_path, monkeypatch) -> None:
    """Empty CONFIG.personal.domains disables the check entirely (operator opt-out)."""
    import lint

    fake_knowledge = tmp_path / "knowledge"
    fake_knowledge.mkdir(parents=True)
    _seed_article(tmp_path, "anything.md", "totally-made-up")

    monkeypatch.setattr(lint.CONFIG.personal, "domains", [])

    ctx = lint.build_context(vault=tmp_path, knowledge_dir=fake_knowledge, state={})
    assert lint.check_domain_value(ctx) == []


# ── 4. query.py argparse accepts --domain ───────────────────────────────


def test_query_argparse_accepts_domain_flag() -> None:
    """The wiki query CLI must parse `--domain <value>` without erroring.

    We don't run the actual query (that would hit the SDK + cost money) —
    we only build the parser the way query.main() does and confirm it
    accepts the flag.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("question", type=str)
    parser.add_argument("--file-back", action="store_true")
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--include-final-only", action="store_true")
    parser.add_argument("--domain", type=str, default=None)

    args = parser.parse_args(["why does X?", "--domain", "personal"])
    assert args.domain == "personal"

    # Default = None when omitted.
    args2 = parser.parse_args(["why does Y?"])
    assert args2.domain is None


def test_query_module_declares_domain_argument() -> None:
    """The actual query.py source declares the --domain flag (regression
    guard against accidental removal in future edits)."""
    query_src = (
        Path(__file__).resolve().parent.parent / "scripts" / "query.py"
    ).read_text(encoding="utf-8")
    assert "--domain" in query_src
    assert "CONFIG.personal.domains" in query_src
