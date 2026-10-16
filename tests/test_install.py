"""`install.sh` end to end (M034-S04-T05): a bare directory becomes a seeded vault through
`wiki seed` after the engine's environment is synced — and nothing calls jq any more.

The installer runs from the checkout and clones the oracle's engine template (the working
tree as one commit, tests/_oracle.py) via `LLM_WIKI_REPO`. PATH holds the uv shim (its
`uv sync` builds a venv of links onto the test venv) and a decoy `jq` that records any call.
HOME is a sandbox.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from ._oracle import REPO_ROOT, build_engine_template, write_uv_shim

INSTALL = REPO_ROOT / "install.sh"


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("engine") / ".wiki")


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    write_uv_shim(bin_dir)
    marker = tmp_path / "jq-was-called"
    decoy = bin_dir / "jq"
    decoy.write_text(f'#!/bin/sh\necho "$@" >> "{marker}"\nexit 99\n', encoding="utf-8")
    decoy.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {"bin": bin_dir, "home": home, "jq_marker": marker}


def _install(
    target: Path, template: Path, machine: dict[str, Path]
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.pathsep.join((str(machine["bin"]), "/usr/bin", "/bin")),
        "HOME": str(machine["home"]),
        "LLM_WIKI_REPO": f"file://{template}",
        "PYTHONUTF8": "1",
    }
    return subprocess.run(
        ["bash", str(INSTALL), str(target)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_a_bare_directory_becomes_a_seeded_vault_without_jq(
    tmp_path: Path, engine_template: Path, machine: dict[str, Path]
) -> None:
    target = tmp_path / "vault"
    target.mkdir()
    run = _install(target, engine_template, machine)
    assert run.returncode == 0, run.stdout + run.stderr
    assert not machine["jq_marker"].exists(), "jq was called: " + machine["jq_marker"].read_text()
    assert "✓ seeded .obsidian/plugins/obsidian-shellcommands/data.json" in run.stdout
    shell = json.loads(
        (target / ".obsidian/plugins/obsidian-shellcommands/data.json").read_text(encoding="utf-8")
    )
    aliases = {c["alias"] for c in shell["shell_commands"]}
    buttons = json.loads(
        (target / ".obsidian/plugins/obsidian-meta-bind-plugin/data.json").read_text(
            encoding="utf-8"
        )
    )["buttonTemplates"]
    dashboard = (target / "dashboard.md").read_text(encoding="utf-8")
    assert set(re.findall(r"BUTTON\[([^\]]+)\]", dashboard)) <= {b["id"] for b in buttons}
    prefix = shell["command_palette_prefix"]
    runs = [a["command"] for b in buttons for a in b["actions"] if a["command"].startswith(prefix)]
    assert {r.removeprefix(prefix) for r in runs} <= aliases


def test_a_headless_install_over_existing_files_keeps_them(
    tmp_path: Path, engine_template: Path, machine: dict[str, Path]
) -> None:
    target = tmp_path / "vault"
    (target / ".obsidian").mkdir(parents=True)
    (target / "AGENTS.md").write_text("the operator's own AGENTS.md\n", encoding="utf-8")
    run = _install(target, engine_template, machine)
    assert run.returncode == 0, run.stdout + run.stderr
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "the operator's own AGENTS.md\n"
    assert "kept existing AGENTS.md" in run.stdout
    assert not machine["jq_marker"].exists()
