"""The behaviour oracle — golden snapshots of the operator-facing payloads.

Green without `--snapshot-update` means a refactor changed nothing an operator, the TUI
or the desktop app can see in `wiki menu --json`, `wiki doctor --quick --json` and
`cli.py help`. See tests/_oracle.py for the fixture vault and the determinism rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._oracle import (
    REPO_ROOT,
    assert_matches_golden,
    build_fixture_vault,
    diff_against_golden,
    doctor_quick_payload,
    dump,
    help_text,
    menu_payload,
    normalise,
    patch_engine_paths,
)


@pytest.fixture
def oracle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The fixture vault, patched into every consumer module; returns the placeholder map
    that normalises its paths away."""
    vault = build_fixture_vault(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    home = patch_engine_paths(monkeypatch, vault, scratch)
    return {str(vault): "<VAULT>", str(home): "<HOME>", str(scratch): "<SCRATCH>", str(REPO_ROOT): "<WIKI>"}


def test_menu_json_matches_golden(oracle, capsys, request) -> None:
    payload = normalise(menu_payload(capsys), placeholders=oracle)
    assert payload["schema"] == 2
    assert_matches_golden(request, "menu.json", dump(payload))


def test_doctor_quick_json_matches_golden(oracle, capsys, monkeypatch, request) -> None:
    payload = normalise(doctor_quick_payload(monkeypatch, capsys), placeholders=oracle)
    assert payload["schema"] == 2
    assert_matches_golden(request, "doctor-quick.json", dump(payload))


def test_help_matches_golden(oracle, request) -> None:
    assert_matches_golden(request, "help.txt", normalise(help_text(), placeholders=oracle))


def test_comparer_reports_a_one_word_title_change(oracle, capsys) -> None:
    """The guard seen failing: a single changed word in one title must surface in the diff."""
    payload = normalise(menu_payload(capsys), placeholders=oracle)
    payload["tools"][0]["title"] = payload["tools"][0]["title"] + " (changed)"
    diff = diff_against_golden("menu.json", dump(payload))
    assert diff is not None
    assert "(changed)" in diff


def test_goldens_are_committed() -> None:
    """A missing golden is a defect of the commit, not a reason to skip."""
    for name in ("menu.json", "doctor-quick.json", "help.txt"):
        assert (REPO_ROOT / "tests" / "golden" / "oracle" / name).exists(), (
            f"tests/golden/oracle/{name} missing — run `uv run pytest tests/test_oracle_payloads.py "
            "--snapshot-update`, review the file, commit it"
        )
