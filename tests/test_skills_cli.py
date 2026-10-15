"""`wiki skills` in Python (M034-S03-T06).

The flows are held byte for byte by the bash oracle's goldens (tests/test_bash_oracle.py:
skills-*). These tests hold what a golden does not reach: what counts as the engine's, the
registry's idempotence, a soft-failing registry write, and that a vault reached through a
symlink is still "this vault" (the bash compared paths as text; Python's paths are resolved).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import skills_cli


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    vault, home = tmp_path / "vault", tmp_path / "home"
    (vault / ".wiki" / "skills" / "use-llm-wiki").mkdir(parents=True)
    (vault / ".wiki" / "skills" / "vault-only").mkdir()
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(skills_cli, "ROOT_DIR", vault)
    monkeypatch.setattr(skills_cli, "WIKI_DIR", vault / ".wiki")
    return {"vault": vault, "home": home, "tmp": tmp_path}


def test_only_links_into_the_engine_skills_are_the_engines(world: dict[str, Path]) -> None:
    dst = world["vault"] / ".claude" / "skills"
    dst.mkdir(parents=True)
    (dst / "ours").symlink_to("../../.wiki/skills/ours")
    (dst / "absolute").symlink_to(world["vault"] / ".wiki" / "skills" / "absolute")
    (dst / "own-dir").mkdir()
    assert skills_cli._engine_owned(dst / "ours")
    assert not skills_cli._engine_owned(dst / "absolute")
    assert not skills_cli._engine_owned(dst / "own-dir")


def test_install_links_the_missing_and_leaves_the_rest(world: dict[str, Path]) -> None:
    dst = world["vault"] / ".claude" / "skills"
    dst.mkdir(parents=True)
    (dst / "vault-only").mkdir()  # the operator's own, under an engine skill's name
    assert skills_cli.install_local() == (1, 0, 1)
    assert os.readlink(dst / "use-llm-wiki") == "../../.wiki/skills/use-llm-wiki"
    assert skills_cli.install_local() == (0, 1, 1)


def test_the_registry_lists_a_vault_once_and_removes_only_it(world: dict[str, Path]) -> None:
    registry = world["home"] / ".config" / "llm-wiki" / "vaults"
    registry.parent.mkdir(parents=True)
    registry.write_text("/elsewhere/other-vault\n", encoding="utf-8")
    skills_cli._registry_add()
    skills_cli._registry_add()
    assert registry.read_text(encoding="utf-8") == f"/elsewhere/other-vault\n{world['vault']}\n"
    skills_cli._registry_remove()
    assert registry.read_text(encoding="utf-8") == "/elsewhere/other-vault\n"


def test_a_registry_that_cannot_be_written_is_a_warning(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    (world["home"] / ".config").write_text("not a directory", encoding="utf-8")
    skills_cli._registry_add()
    assert "vault not registered" in capsys.readouterr().out


def test_a_vault_reached_through_a_symlink_is_still_this_vault(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The bash wrote the global link and the registry line through the path it was started
    on, e.g. `~/vault → /Volumes/data/vault`; Python's paths are resolved. Comparing them as
    text called this vault another one, and `uninstall --global` left its link behind."""
    alias = world["tmp"] / "alias-vault"
    alias.symlink_to(world["vault"])
    link = world["home"] / ".claude" / "skills" / "use-llm-wiki"
    link.parent.mkdir(parents=True)
    link.symlink_to(alias / ".wiki" / "skills" / "use-llm-wiki")
    registry = world["home"] / ".config" / "llm-wiki" / "vaults"
    registry.parent.mkdir(parents=True)
    registry.write_text(f"{alias}\n", encoding="utf-8")

    skills_cli.status()
    assert "linked → this vault" in capsys.readouterr().out
    skills_cli._registry_add()
    assert registry.read_text(encoding="utf-8") == f"{alias}\n"  # no second line for it
    assert skills_cli.uninstall_global() == 1
    assert not link.is_symlink()
    assert registry.read_text(encoding="utf-8") == ""


def test_flags_go_anywhere_and_an_unknown_command_is_refused(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[bool | None] = []
    monkeypatch.setattr(skills_cli, "install", lambda global_flag: seen.append(global_flag) or 0)
    assert skills_cli.main(["--global", "install"]) == 0
    assert skills_cli.main([]) == 0
    assert seen == [True, None]
    assert skills_cli.main(["bogus"]) == 1
    out, err = capsys.readouterr()
    assert "unknown: wiki skills bogus" in err
    assert "wiki skills sync" in out  # the help follows
