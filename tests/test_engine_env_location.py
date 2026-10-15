"""lib/common.sh — where the engine's Python environment lives.

The rule has ONE home (bash, sourced by the `wiki` dispatcher); Python only
reads its result via UV_PROJECT_ENVIRONMENT / sys.prefix. These pin the rule
and the two places that must carry it literally: the exported variable and
the agent hook commands (core/agents.py, written by `wiki hooks install`),
because hook processes are spawned by the agent with the agent's environment,
not by `wiki`.

Why it exists: lxw 2026-09-17 — the vault sits in iCloud Drive, the in-vault
.venv got evicted while the bundled Claude CLI was running, the kernel
SIGKILLed it (`Taskgated Invalid Signature`), and the 08-26 symlink fix had
been silently undone by iCloud's conflict handling.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import agents

from ._oracle import (
    build_engine_template,
    build_fixture_vault,
    install_engine,
    run_wiki,
    write_uv_shim,
)

ENGINE = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="bash + jq required for the dispatcher libs",
)


def _bash(script: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", **(env or {})},
    )
    return result.stdout


def _source(vault: str, extra_env: dict | None = None, tail: str = "") -> str:
    return _bash(
        f"WIKI_DIR='{vault}/.wiki' ROOT_DIR='{vault}'; source '{ENGINE}/lib/common.sh'; {tail}",
        env=extra_env,
    )


ICLOUD_VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
CLOUDSTORAGE_VAULT = "/h/Library/CloudStorage/Dropbox/notes"
PLAIN_VAULT = "/h/Sync/vault"


def test_icloud_vault_gets_out_of_vault_environment():
    out = _source(ICLOUD_VAULT, tail='printf "%s" "$UV_PROJECT_ENVIRONMENT"')
    assert out == "/h/.venvs/lxw-wiki"


def test_cloudstorage_vault_gets_out_of_vault_environment():
    out = _source(CLOUDSTORAGE_VAULT, tail='printf "%s" "$UV_PROJECT_ENVIRONMENT"')
    assert out == "/h/.venvs/notes-wiki"


def test_plain_vault_keeps_uv_default():
    out = _source(PLAIN_VAULT, tail='printf "[%s]" "${UV_PROJECT_ENVIRONMENT:-}"')
    assert out == "[]"


def test_operator_override_always_wins():
    out = _source(
        ICLOUD_VAULT,
        extra_env={"UV_PROJECT_ENVIRONMENT": "/elsewhere/env"},
        tail='printf "%s" "$UV_PROJECT_ENVIRONMENT"',
    )
    assert out == "/elsewhere/env"


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("env-engine") / ".wiki")


def test_an_install_in_a_cloud_vault_writes_the_environment_into_every_hook(
    tmp_path: Path, engine_template: Path
) -> None:
    """End to end, through the real `wiki`: lib/common.sh exports UV_PROJECT_ENVIRONMENT for
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
