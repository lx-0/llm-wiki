"""`--json` through the bash layer: stdout is the payload alone.

M033-S04-T06: the live `wiki query --brief --json` on the scratch vault answered
`wiki query\\n\\n{…}` — the dispatcher's banner ahead of the payload (the desktop parsed
around it from the first `{`). The bash-native `wiki dream list-candidates --json` printed
its banner the same way. Real bash layer (`wiki` + `lib/`); `uv` is a stub first on PATH
that prints a fixed JSON payload, so stdout is exactly what a consumer would parse.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = '{"stub": true}'


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)  # the dispatcher's fail-closed vault guard
    engine = vault / ".wiki"
    engine.mkdir()
    shutil.copy2(REPO / "wiki", engine / "wiki")
    shutil.copytree(REPO / "lib", engine / "lib")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "uv"
    stub.write_text(f"#!/bin/sh\nprintf '%s\\n' '{PAYLOAD}'\n", encoding="utf-8")
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(home))
    return vault


def _wiki(vault: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(vault / ".wiki" / "wiki"), *args],
        cwd=vault,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_dream_list_candidates_json_prints_only_the_payload(vault: Path) -> None:
    r = _wiki(vault, "dream", "list-candidates", "--json")

    assert r.returncode == 0, r.stderr
    assert r.stdout == PAYLOAD + "\n"
    assert json.loads(r.stdout) == {"stub": True}


def test_dream_list_candidates_keeps_its_banner_for_humans(vault: Path) -> None:
    r = _wiki(vault, "dream", "list-candidates", "--limit", "5")

    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("wiki dream list-candidates")
    assert r.stdout.endswith(PAYLOAD + "\n")
