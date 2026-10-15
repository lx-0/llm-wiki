"""`wiki hooks` in Python (M034-S03-T05).

The flows are held byte for byte by the bash oracle's goldens (tests/test_bash_oracle.py:
hooks-*, status, setup-with-hooks). These tests hold what a golden does not show at a
glance: the byte-counted padding, the states of the table, that a config no merge can read
is left as it was, and that an install and an uninstall give another tool's config back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import hooks_cli


def _fd(*answers: str) -> int:
    """A pipe holding the scripted answers to the prompts, read byte by byte."""
    read_end, write_end = os.pipe()
    os.write(write_end, "".join(answers).encode())
    os.close(write_end)
    return read_end


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    home, vault = tmp_path / "home", tmp_path / "vault"
    home.mkdir()
    vault.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(hooks_cli, "ROOT_DIR", vault)
    monkeypatch.setattr(hooks_cli, "WIKI_DIR", vault / ".wiki")
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    return {"home": home, "vault": vault}


def _user_settings(world: dict[str, Path], text: str) -> Path:
    cfg = world["home"] / ".claude" / "settings.json"
    cfg.parent.mkdir()
    cfg.write_text(text, encoding="utf-8")
    return cfg


def test_cells_are_padded_by_bytes_as_bash_printf_does() -> None:
    """`%-30s` counts bytes: the em dash takes three of the thirty."""
    assert hooks_cli._pad("—", 30) == "—" + " " * 27
    assert hooks_cli._pad("installed", 30) == "installed" + " " * 21


def test_an_unreadable_config_shows_as_unreadable(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _user_settings(world, "{ not json")
    hooks_cli.status_table()
    row = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("claude"))
    assert row.split()[1] == "unreadable"


def test_install_leaves_an_unreadable_config_as_it_was(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _user_settings(world, "{ not json")

    code = hooks_cli.install(fd=_fd("1\n", "1\n", "y\n"))

    out, err = capsys.readouterr()
    assert code == 1
    assert cfg.read_text(encoding="utf-8") == "{ not json"
    assert [p.name for p in cfg.parent.iterdir()] == ["settings.json"]  # no backup, no .tmp
    assert "✗ claude (user): " in err
    assert "is not valid JSON — left as it was" in err
    assert "✗ 1 of 1 hook installs failed — see above." in err
    assert "Done" not in out


def test_install_then_uninstall_gives_another_tools_config_back(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    other = {"hooks": [{"type": "command", "command": "other-tool"}]}
    before = {"permissions": {"allow": ["Bash(ls:*)"]}, "hooks": {"SessionStart": [other]}}
    cfg = _user_settings(world, json.dumps(before))

    assert hooks_cli.install(fd=_fd("1\n", "1\n", "y\n")) == 0
    assert "SessionEnd" in json.loads(cfg.read_text(encoding="utf-8"))["hooks"]
    assert hooks_cli.uninstall(fd=_fd("\n", "1\n", "y\n")) == 0

    assert json.loads(cfg.read_text(encoding="utf-8")) == before
    backups = [p for p in cfg.parent.iterdir() if ".bak." in p.name]
    assert len(backups) == 2  # one per write; the pre-install original among them
    assert before in [json.loads(b.read_text(encoding="utf-8")) for b in backups]


def test_an_unknown_subcommand_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert hooks_cli.main(["bogus"]) == 1
    out, err = capsys.readouterr()
    assert "unknown: wiki hooks bogus" in err
    assert "wiki hooks uninstall" in out  # the help follows
