"""The bash oracle (M034-S01) — what the bash-owned commands print, recorded BEFORE any of
them is ported to Python.

Each case runs the real `wiki` out of an engine copy in the fixture vault (see
tests/_oracle.py: `build_engine_copy`, `write_uv_shim`, `run_wiki`) with no TTY and a
scratch HOME, and compares the normalised exit code, stdout and stderr against
tests/golden/bash/<name>.txt. The goldens are the contract the S01–S05 ports are held to: a
port must reproduce them, or change them in the same commit with the reason.

Read-only commands only. The mutating ones (config set, hooks / skills install, seed,
install-shortcut) are S01-T02's, and `update` is S05-T01's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ._oracle import (
    BASH_GOLDEN_DIR,
    REPO_ROOT,
    assert_matches_golden,
    build_engine_copy,
    build_fixture_vault,
    dump,
    normalise,
    normalise_text,
    render_run,
    run_wiki,
    write_uv_shim,
)

READ_ONLY: dict[str, tuple[str, ...]] = {
    # the catalogue and the bare entry without a TTY
    "help": ("help",),
    "bare-no-tty": (),
    # the bash-owned help texts
    "config-help": ("config", "--help"),
    "hooks-help": ("hooks", "--help"),
    "setup-help": ("setup", "--help"),
    "skills-help": ("skills", "--help"),
    "update-help": ("update", "--help"),
    "seed-help": ("seed", "--help"),
    "menu-help": ("menu", "--help"),
    "doctor-help": ("doctor", "--help"),
    "dream-help": ("dream", "--help"),
    "dream-entity-help": ("dream-entity", "--help"),
    "install-shortcut-help": ("install-shortcut", "--help"),
    # state readers
    "version": ("version",),
    "status": ("status",),
    "menu-no-tty": ("menu",),
    "menu-json": ("menu", "--json"),
    "doctor-quick-json": ("doctor", "--quick", "--json"),
    "config-get": ("config", "get", "models.compile_model"),
    "config-keys": ("config", "keys"),
    "config-path": ("config", "path"),
    "config-status": ("config", "status"),
    "config-unknown": ("config", "bogus"),
    "hooks-status": ("hooks", "status"),
    "skills-status": ("skills", "status"),
}


@pytest.fixture(scope="module")
def bash_vault(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One fixture vault with an engine copy, a scratch HOME and the uv shim — built once:
    every case here only reads."""
    root = tmp_path_factory.mktemp("bash-oracle")
    vault = build_fixture_vault(root)
    build_engine_copy(vault)
    # `config status` probes Ollama at the configured URL: a closed local port answers the
    # same on every machine (the default localhost:11434 would not on one running Ollama).
    (vault / ".wiki" / "config.yaml").write_text(
        "# bash-oracle fixture config — defaults, Ollama on a closed port\n"
        "models:\n  ollama_url: http://127.0.0.1:9\n",
        encoding="utf-8",
    )
    home = root / "home"
    home.mkdir()
    bin_dir = root / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "home": home, "bin": bin_dir, "root": root}


def _placeholders(env: dict[str, Path]) -> dict[str, str]:
    return {
        str(env["vault"]): "<VAULT>",
        str(env["home"]): "<HOME>",
        str(env["bin"]): "<BIN>",
        str(env["root"]): "<ROOT>",
        str(REPO_ROOT): "<REPO>",
        str(Path(sys.executable).parent.parent): "<VENV>",
    }


# Counts of the machine, not the vault: the eviction check walks the interpreter's env,
# whose file count differs between a laptop and the CI runner (324 vs 321 on first run).
_MACHINE_COUNTS = frozenset({"scanned"})


def _blank_machine_counts(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("N" if k in _MACHINE_COUNTS else _blank_machine_counts(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_blank_machine_counts(v) for v in value]
    return value


def record(env: dict[str, Path], args: tuple[str, ...]) -> str:
    run = run_wiki(env["vault"], env["home"], env["bin"], *args)
    placeholders = _placeholders(env)
    if "--json" in args and run.returncode in (0, 1):
        # A JSON payload is compared as parsed + normalised JSON (the M033 oracle's rule:
        # digits in free text → N), so a humanised age cannot flake it. Paths and git
        # revisions go first, on the raw text: the engine copy's commit hash depends on the
        # tree it was copied from.
        raw = normalise_text(run.stdout, placeholders=placeholders)
        payload = _blank_machine_counts(normalise(json.loads(raw), placeholders=placeholders))
        run = type(run)(run.args, run.returncode, dump(payload), run.stderr)
    return render_run(args, run, placeholders)


@pytest.mark.parametrize("name", sorted(READ_ONLY))
def test_bash_command_matches_golden(bash_vault, request, name: str) -> None:
    text = record(bash_vault, READ_ONLY[name])
    assert_matches_golden(request, f"{name}.txt", text, BASH_GOLDEN_DIR)
