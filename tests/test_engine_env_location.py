"""Where the engine's Python environment lives.

The rule has two copies, and nothing can make them one: the bootstrap `wiki` needs it before
any Python runs (to find the interpreter), and `core/health/engine.py` judges a vault with
it. `CLOUD_RULE` is the one table of cases both are held to. Two more places carry the
rule's result literally: the exported UV_PROJECT_ENVIRONMENT, and the agent hook commands
(core/agents.py, written by `wiki hooks install`), because the agent spawns hook processes
with its own environment, not with `wiki`'s.

Why it exists: lxw 2026-09-17 — the vault sits in iCloud Drive, the in-vault
.venv got evicted while the bundled Claude CLI was running, the kernel
SIGKILLed it (`Taskgated Invalid Signature`), and the 08-26 symlink fix had
been silently undone by iCloud's conflict handling.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core import agents
from core.health.engine import _in_cloud_path

from ._oracle import (
    build_engine_template,
    build_fixture_vault,
    install_engine,
    run_wiki,
    write_uv_shim,
)

ENGINE = Path(__file__).resolve().parent.parent

# Where a vault sits (under the test's temp dir) → whether it is cloud-synced, so that its
# environment moves to ~/.venvs/<vault>-wiki.
CLOUD_RULE = [
    ("Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw", True),
    ("Library/CloudStorage/Dropbox/notes", True),
    ("Library/CloudStorage/GoogleDrive-op@example.com/My Drive/vault", True),
    ("Sync/vault", False),
    ("Documents/Mobile Documents/vault", False),  # the marker is `/Library/Mobile Documents/`
]


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("env-engine") / ".wiki")


def _first_run(
    tmp_path: Path, template: Path, where: str, extra_env: dict[str, str] | None = None
) -> tuple[Path, Path]:
    """A vault at ``where``, run once through the real `wiki` (`version`): the bootstrap
    syncs the environment where the rule puts it, and the uv shim creates it there.
    Returns the vault and HOME."""
    vault = tmp_path / where
    vault.mkdir(parents=True)
    install_engine(vault, template)
    home = tmp_path / "home"
    home.mkdir()
    write_uv_shim(tmp_path / "bin")
    run = run_wiki(vault, home, tmp_path / "bin", "version", extra_env=extra_env)
    assert run.returncode == 0, run.stderr
    return vault, home


@pytest.mark.parametrize(("where", "cloud"), CLOUD_RULE)
def test_the_bootstrap_puts_the_environment_where_the_rule_says(
    tmp_path: Path, engine_template: Path, where: str, cloud: bool
) -> None:
    vault, home = _first_run(tmp_path, engine_template, where)
    outside = home / ".venvs" / f"{vault.name}-wiki" / "bin" / "python"
    inside = vault / ".wiki" / ".venv" / "bin" / "python"
    assert (outside.exists(), inside.exists()) == (cloud, not cloud)


@pytest.mark.parametrize(("where", "cloud"), CLOUD_RULE)
def test_doctor_judges_the_same_paths_cloud_synced(tmp_path: Path, where: str, cloud: bool):
    assert _in_cloud_path(tmp_path / where / ".wiki") is cloud


def test_operator_override_always_wins(tmp_path: Path, engine_template: Path) -> None:
    elsewhere = tmp_path / "elsewhere" / "env"
    vault, home = _first_run(
        tmp_path,
        engine_template,
        CLOUD_RULE[0][0],
        extra_env={"UV_PROJECT_ENVIRONMENT": str(elsewhere)},
    )
    assert (elsewhere / "bin" / "python").exists()
    assert not (home / ".venvs").exists()
    assert not (vault / ".wiki" / ".venv").exists()


def test_an_install_in_a_cloud_vault_writes_the_environment_into_every_hook(
    tmp_path: Path, engine_template: Path
) -> None:
    """End to end, through the real `wiki`: the bootstrap exports UV_PROJECT_ENVIRONMENT for
    a vault in iCloud Drive, and `wiki hooks install` writes it into each agent's hook
    commands. Was two tests that sourced lib/agents.sh (deleted in M034-S03-T07)."""
    cloud = tmp_path / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents"
    vault = build_fixture_vault(cloud)
    wiki = install_engine(vault, engine_template)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    write_uv_shim(bin_dir)

    run = run_wiki(vault, home, bin_dir, "hooks", "install", stdin="1 2 3 4\n1\ny\n")

    assert run.returncode == 0, run.stderr
    prefix = f"cd '{wiki}' && UV_PROJECT_ENVIRONMENT='{home}/.venvs/{vault.name}-wiki' "
    for spec in agents.AGENTS:
        commands = agents.wiki_commands(json.loads((home / spec.config).read_text()))
        assert commands, f"{spec.name}: no hook commands written"
        for command in commands:
            assert command.startswith(f"{prefix}uv run python hooks/"), command


def test_the_hook_command_runs_for_a_vault_path_with_an_apostrophe(tmp_path: Path):
    """A vault called "Alex's Vault": the hook command quotes its paths for the shell the
    agent runs it in. Wrapped in bare '…', the apostrophe ended the quote early and every
    hook died on a syntax error (exit 2), so no session in that vault was ever captured
    (0.7.15). The vault is cloud-synced, so the environment prefix (~/.venvs/Alex's
    Vault-wiki) is quoted too."""
    vault = tmp_path / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Alex's Vault"
    (vault / ".wiki").mkdir(parents=True)
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    uv = stub_bin / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s|%s|%s" "$PWD" "$UV_PROJECT_ENVIRONMENT" "$*"\n')
    uv.chmod(0o755)
    venv = "/h/.venvs/Alex's Vault-wiki"
    cmd = agents.hook_cmd("hooks/session-start.py", wiki_dir=vault / ".wiki", venv=venv)

    ran = subprocess.run(
        ["sh", "-c", cmd],
        capture_output=True,
        text=True,
        env={"PATH": f"{stub_bin}:/usr/bin:/bin"},
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    cwd, env_dir, args = ran.stdout.split("|")
    assert Path(cwd).resolve() == (vault / ".wiki").resolve()
    assert env_dir == venv
    assert args == "run python hooks/session-start.py"
    # …and `wiki hooks status` still recognises what the installer writes.
    cfg = tmp_path / "settings.json"
    cfg.write_text(agents.render(agents.payload("claude", wiki_dir=vault / ".wiki", venv=venv)))
    assert agents.hooks_installed(cfg)
