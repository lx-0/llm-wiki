"""`core/backup.py` (M034-S03-T03) — the engine's one backup helper.

Backups are named to the second. Two within one second shared a name, and the second replaced
the first: the pre-change original. Recording the bash hooks oracle found it (S03-T02), and a
grep found five Python writers with the same flaw; they all go through here now.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core import backup

ENGINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup, "stamp", lambda: "20261015-120000")


def test_two_backups_in_one_second_keep_both(tmp_path: Path, one_second: None) -> None:
    f = tmp_path / "f.md"
    f.write_text("original", encoding="utf-8")
    first = backup.backup(f)
    f.write_text("changed", encoding="utf-8")
    second = backup.backup(f)

    assert first == tmp_path / "f.md.bak.20261015-120000"
    assert second == tmp_path / "f.md.bak.20261015-120000-2"
    assert first.read_text(encoding="utf-8") == "original"
    assert second.read_text(encoding="utf-8") == "changed"


def test_a_missing_file_has_no_backup(tmp_path: Path) -> None:
    assert backup.backup(tmp_path / "nope.md") is None


def test_the_clash_counter_goes_before_the_extension(tmp_path: Path, one_second: None) -> None:
    first = backup.backup_path(tmp_path, "procmail-backup-acct-", ".txt")
    first.write_text("x", encoding="utf-8")

    assert first.name == "procmail-backup-acct-20261015-120000.txt"
    again = backup.backup_path(tmp_path, "procmail-backup-acct-", ".txt")
    assert again.name == "procmail-backup-acct-20261015-120000-2.txt"


def test_the_stamp_is_compact() -> None:
    assert re.fullmatch(r"\d{8}-\d{6}", backup.stamp())


def test_the_mail_adapters_keep_both_backups_from_one_second(
    tmp_path: Path, one_second: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two writers a batch reaches: several filter rules rewrite the same file within
    milliseconds. Their names keep their old shape."""
    from adapters.mailbox import allinkl, thunderbird

    rules = tmp_path / "msgFilterRules.dat"
    rules.write_text("v1", encoding="utf-8")
    first = thunderbird._backup(rules)
    rules.write_text("v2", encoding="utf-8")
    second = thunderbird._backup(rules)
    assert first is not None and second is not None
    assert [first.name, second.name] == [
        "msgFilterRules.dat.backup-20261015-120000",
        "msgFilterRules.dat.backup-20261015-120000-2",
    ]
    assert first.read_text(encoding="utf-8") == "v1"

    monkeypatch.setattr(allinkl, "RAW_DIR", tmp_path / "raw")
    one = allinkl._backup("recipe v1", "acct")
    two = allinkl._backup("recipe v2", "acct")
    assert [one.name, two.name] == [
        "procmail-backup-acct-20261015-120000.txt",
        "procmail-backup-acct-20261015-120000-2.txt",
    ]
    assert one.read_text(encoding="utf-8") == "recipe v1"


_STAMP = re.compile(r"""strftime\(\s*["']%Y%m%d-%H%M%S["']\s*\)""")
_NOT_A_BACKUP = {"scripts/agent_task.py": "a log file's name"}


def test_no_second_backup_stamp_outside_the_seam() -> None:
    """Five writers named their backups to the second on their own, each free to overwrite
    an earlier one. Only core/backup.py formats that stamp now."""
    offenders = [
        rel
        for path in sorted((ENGINE / "scripts").rglob("*.py"))
        if (rel := path.relative_to(ENGINE).as_posix()) != "scripts/core/backup.py"
        and rel not in _NOT_A_BACKUP
        and _STAMP.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
