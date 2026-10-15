"""`wiki install-shortcut` in Python (M034-S02-T04) — `scripts/shortcut_cli.py`.

The bash oracle holds the parity paths on a fixture HOME whose PATH never holds
`~/.local/bin` (`install-shortcut*` goldens); these tests add the branches it cannot reach —
on PATH, an equivalent link — and the refusal that replaced the bash's `rm -f` of a regular
file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import shortcut_cli


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    target = tmp_path / "vault" / ".wiki" / "wiki"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)
    monkeypatch.setattr(shortcut_cli, "TARGET", target)
    return home


def _link(home: Path) -> Path:
    return home / ".local" / "bin" / "wiki"


def test_creates_the_link_and_prints_the_rc_line(home, capsys):
    assert shortcut_cli.install() == 0
    assert os.readlink(_link(home)) == str(shortcut_cli.TARGET)
    out = capsys.readouterr().out
    assert f"✓ linked: {_link(home)} → {shortcut_cli.TARGET}" in out
    assert f"! {home / '.local' / 'bin'} is NOT on PATH" in out
    assert '  export PATH="$HOME/.local/bin:$PATH"\n' in out  # with its quotes


def test_on_path_says_so_and_prints_no_rc_line(home, capsys, monkeypatch):
    monkeypatch.setenv("PATH", f"/usr/bin:{home / '.local' / 'bin'}:/bin")
    shortcut_cli.install()
    out = capsys.readouterr().out
    assert "is on PATH — typing `wiki` from any cwd will work" in out
    assert "export PATH" not in out


def test_print_only_writes_nothing(home, capsys):
    assert shortcut_cli.install(print_only=True) == 0
    assert not _link(home).exists()
    assert f"would create: {_link(home)} → {shortcut_cli.TARGET}" in capsys.readouterr().out


def test_an_equivalent_link_counts_as_linked(home, capsys, tmp_path):
    """/tmp → /private/tmp on macOS: the same file through another path is not replaced."""
    alias = tmp_path / "alias"
    alias.symlink_to(shortcut_cli.TARGET.parent.parent)  # alias → the vault
    _link(home).parent.mkdir(parents=True)
    _link(home).symlink_to(alias / ".wiki" / "wiki")
    assert shortcut_cli.install() == 0
    assert "✓ already linked:" in capsys.readouterr().out
    assert os.readlink(_link(home)) == str(alias / ".wiki" / "wiki")  # untouched


def test_a_link_to_another_vault_is_replaced(home, capsys, tmp_path):
    _link(home).parent.mkdir(parents=True)
    _link(home).symlink_to(tmp_path / "other" / ".wiki" / "wiki")
    assert shortcut_cli.install() == 0
    out = capsys.readouterr().out
    assert f"replacing existing: {_link(home)} → {tmp_path / 'other' / '.wiki' / 'wiki'}" in out
    assert os.readlink(_link(home)) == str(shortcut_cli.TARGET)


def test_a_regular_file_is_refused_not_deleted(home, capsys):
    """The bash `rm -f`'d whatever sat there — another program called `wiki` included."""
    _link(home).parent.mkdir(parents=True)
    _link(home).write_text("another tool", encoding="utf-8")
    assert shortcut_cli.install() == 1
    assert _link(home).read_text(encoding="utf-8") == "another tool"
    assert "is not a symlink" in capsys.readouterr().err


def test_an_engine_without_its_entry_errors(home, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(shortcut_cli, "TARGET", tmp_path / "missing" / "wiki")
    assert shortcut_cli.install() == 1
    assert "is not executable" in capsys.readouterr().err
