"""`--json` end to end through `wiki`: stdout is the payload alone.

M033-S04-T06: the live `wiki query --brief --json` on the scratch vault answered
`wiki query\\n\\n{…}` — the dispatcher's banner ahead of the payload (the desktop parsed
around it from the first `{`). The then bash-native `wiki dream list-candidates --json`
printed its banner the same way. Since M034-S01-T06 the dream routing lives in the catalogue
(`cli.run_command` owns the banner rule; `tests/test_cli.py` pins it per route), and this
file holds the whole path: the real `wiki` out of an engine copy in the oracle's fixture
vault, through the one hop, into `dream.py` — stdout is exactly what a consumer parses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ._oracle import build_engine_copy, build_fixture_vault, run_wiki, write_uv_shim


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("json-banner")
    vault = build_fixture_vault(root)
    build_engine_copy(vault)
    home = root / "home"
    home.mkdir()
    bin_dir = root / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "home": home, "bin": bin_dir}


def test_dream_list_candidates_json_prints_only_the_payload(env: dict[str, Path]) -> None:
    r = run_wiki(env["vault"], env["home"], env["bin"], "dream", "list-candidates", "--json")

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)  # nothing ahead of the payload, nothing after it
    assert [c["slug"] for c in payload] == ["sam-rivera", "llm-wiki"]


def test_dream_list_candidates_keeps_its_banner_for_humans(env: dict[str, Path]) -> None:
    r = run_wiki(env["vault"], env["home"], env["bin"], "dream", "list-candidates")

    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("wiki dream list-candidates\n")
    assert "sam-rivera" in r.stdout
