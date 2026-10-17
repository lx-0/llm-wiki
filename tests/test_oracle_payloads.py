"""The behaviour oracle — golden snapshots of the operator-facing payloads.

Green without `--snapshot-update` means a refactor changed nothing an operator, the TUI
or the desktop app can see in `wiki menu --json`, `wiki doctor --quick --json` and
`cli.py help`. See tests/_oracle.py for the fixture vault and the determinism rules.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
    normalise_text,
    patch_engine_paths,
    tree_manifest,
)


@pytest.fixture
def oracle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The fixture vault, patched into every consumer module; returns the placeholder map
    that normalises its paths away."""
    vault = build_fixture_vault(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    home = patch_engine_paths(monkeypatch, vault, scratch)
    return {
        str(vault): "<VAULT>",
        str(home): "<HOME>",
        str(scratch): "<SCRATCH>",
        str(REPO_ROOT): "<WIKI>",
    }


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


def test_patching_loads_every_collector_before_home_moves(tmp_path: Path) -> None:
    """A collector module first imported under the scratch HOME freezes its `Path.home()`
    constants there (`scan_browser.CHROME_PROFILE`) and outlives the test — `doctor --quick`
    reaches `all_collectors()` after the patch. `import collectors` used to import them all;
    since the registry went lazy (M034-S06-T03) it imports none. A fresh interpreter, because
    in the suite another test has usually imported them first."""
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "import collectors\n"
        "from tests import _oracle\n"
        f"root = Path({str(tmp_path)!r})\n"
        "(root / 'scratch').mkdir()\n"
        "vault = _oracle.build_fixture_vault(root)\n"
        "_oracle.patch_engine_paths(pytest.MonkeyPatch(), vault, root / 'scratch')\n"
        "collectors.all_collectors()\n"
        "print(sys.modules['collectors.scan_browser'].CHROME_PROFILE)\n"
    )
    paths = [REPO_ROOT / "scripts", REPO_ROOT / "hooks", REPO_ROOT]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in paths)}
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert str(tmp_path) not in done.stdout


def test_comparer_reports_a_one_word_title_change(oracle, capsys) -> None:
    """The guard seen failing: a single changed word in one title must surface in the diff."""
    payload = normalise(menu_payload(capsys), placeholders=oracle)
    payload["tools"][0]["title"] = payload["tools"][0]["title"] + " (changed)"
    diff = diff_against_golden("menu.json", dump(payload))
    assert diff is not None
    assert "(changed)" in diff


def test_a_large_files_hash_survives_normalising(tmp_path: Path) -> None:
    """A file over the inline limit is recorded by size and sha256. The revision rule took
    the hash for a git revision and erased it, so a changed file of the same size matched
    its golden (M034-S04-T01)."""
    big = tmp_path / "big.json"

    def recorded(content: str) -> str:
        big.write_text(content, encoding="utf-8")
        return normalise_text(tree_manifest(tmp_path)["big.json"], placeholders={})

    assert recorded("x" * 9000) != recorded("y" * 9000)


def test_goldens_are_committed() -> None:
    """A missing golden is a defect of the commit, not a reason to skip."""
    for name in ("menu.json", "doctor-quick.json", "help.txt"):
        assert (REPO_ROOT / "tests" / "golden" / "oracle" / name).exists(), (
            f"tests/golden/oracle/{name} missing — run `uv run pytest tests/test_oracle_payloads.py "
            "--snapshot-update`, review the file, commit it"
        )
