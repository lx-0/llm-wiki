"""`wiki collect <name> -- <flags>` (M034-S06-T04): everything after `--` goes to the
collector module's own `main(argv)` — screenshots' `--backfill`, browser's `--source`, tabs'
`--backup-dir`, youtube's `--url`. It replaced three by-path entry scripts, which the docs
taught as `uv run --project .wiki python .wiki/scripts/scan_*.py …`; on a vault in iCloud
Drive that form ignored the engine's environment and rebuilt `.wiki/.venv` inside the vault.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import types

import pytest

import collectors as collectors_pkg
from collectors import cli


def _fake_collector_module(monkeypatch, name: str, *, with_main: bool = True, rc: int = 0) -> dict:
    seen: dict = {}
    module = types.ModuleType(f"collectors.fake_{name}")
    if with_main:

        def main(argv: list[str] | None = None) -> int:
            seen["argv"] = argv
            return rc

        module.main = main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(collectors_pkg.MODULES, name, module.__name__)
    return seen


def test_the_argv_splits_at_the_first_double_dash():
    assert cli._split_tail(["screenshots", "--", "--backfill", "7", "--", "x"]) == (
        ["screenshots"],
        ["--backfill", "7", "--", "x"],
    )
    assert cli._split_tail(["email", "--incremental"]) == (["email", "--incremental"], None)


def test_the_tail_reaches_the_collectors_main(monkeypatch):
    seen = _fake_collector_module(monkeypatch, "fakescan", rc=3)

    with pytest.raises(SystemExit) as exc:
        cli._run_direct("fakescan", ["--backfill", "7", "--dry-run"])

    assert exc.value.code == 3
    assert seen["argv"] == ["--backfill", "7", "--dry-run"]


def test_a_collector_without_flags_of_its_own_says_which_have_them(monkeypatch, capsys):
    _fake_collector_module(monkeypatch, "plain", with_main=False)

    with pytest.raises(SystemExit) as exc:
        cli._run_direct("plain", ["--x"])

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "'plain' has no flags of its own" in err
    assert "screenshots" in err  # one that has


def test_an_unknown_collector_with_a_tail_is_the_usual_error(capsys):
    with pytest.raises(SystemExit) as exc:
        cli._run_direct("nope", ["--x"])

    assert exc.value.code == 1
    assert "no collector registered with name 'nope'" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["screenshots", "browser", "tabs", "youtube"])
def test_the_four_direct_clis_parse_the_argv_they_are_given(name: str):
    module = importlib.import_module(collectors_pkg.MODULES[name])
    assert "argv" in inspect.signature(module.main).parameters
    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])
    assert exc.value.code == 0
