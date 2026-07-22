"""Machine-readable CLI seams for GUI/agent consumers (C07).

`wiki doctor --json` / `wiki menu --json` set the precedent: every surface the
desktop app consumes gets a structured output mode so engine log wording stays
free to change. This file covers the three seams added in the C07 follow-up:

- `wiki collect --list --json`   (collectors/cli.py)
- `wiki compile --progress-json` (compile.py PROGRESS lines)
- `wiki query --json`            (query.py; flag exclusivity only — the answer
                                  path needs a live SDK call, and the payload
                                  shape is pinned by the desktop parser tests)

The triage seam (`wiki triage list --json`) is covered in
tests/test_triage_record_contract.py next to the record-format contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import collectors as collectors_pkg
from collectors import cli
from collectors.base import CollectorSpec

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fake_collector(name: str, *, configured: bool, piggyback: bool):
    class _Fake:
        SPEC = CollectorSpec(
            name=name,
            output_subfolder=f"raw/{name}",
            piggyback_default=piggyback,
        )

        def is_configured(self) -> bool:
            return configured

    return _Fake()


def test_collect_list_json_payload(monkeypatch, capsys):
    fakes = [
        _fake_collector("email", configured=True, piggyback=True),
        _fake_collector("browser", configured=False, piggyback=False),
    ]
    monkeypatch.setattr(collectors_pkg, "all_collectors", lambda: fakes)

    with pytest.raises(SystemExit) as exc:
        cli._list(as_json=True)

    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {
        "collectors": [
            {"name": "email", "configured": True, "output": "raw/email",
             "piggyback": "auto"},
            {"name": "browser", "configured": False, "output": "raw/browser",
             "piggyback": "manual-only"},
        ]
    }


def test_collect_list_human_table_unchanged(monkeypatch, capsys):
    """Default --list stays the human table — the JSON mode is additive."""
    fakes = [_fake_collector("email", configured=True, piggyback=True)]
    monkeypatch.setattr(collectors_pkg, "all_collectors", lambda: fakes)

    with pytest.raises(SystemExit) as exc:
        cli._list()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "NAME" in out and "✓" in out


def test_compile_emit_progress_line_shape(capsys):
    import compile as compile_mod

    compile_mod._emit_progress(True, 3, 12)
    line = capsys.readouterr().out.strip()
    assert line.startswith("PROGRESS ")
    assert json.loads(line[len("PROGRESS "):]) == {"current": 3, "total": 12}


def test_compile_emit_progress_off_by_default(capsys):
    import compile as compile_mod

    compile_mod._emit_progress(False, 3, 12)
    assert capsys.readouterr().out == ""


def test_query_json_and_file_back_are_mutually_exclusive():
    """--json answers in-line only; combined with --file-back it exits 2
    before any SDK call (fast — the guard runs right after argparse)."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "query.py"),
         "q", "--json", "--file-back"],
        capture_output=True, text=True, timeout=30,
        cwd=REPO_ROOT / "scripts",
    )
    assert proc.returncode == 2
    assert "mutually exclusive" in proc.stderr
