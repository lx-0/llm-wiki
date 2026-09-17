"""lib/common.sh — where the engine's Python environment lives.

The rule has ONE home (bash, sourced by the `wiki` dispatcher); Python only
reads its result via UV_PROJECT_ENVIRONMENT / sys.prefix. These pin the rule
and the two places that must carry it literally: the exported variable and
the agent hook commands (lib/agents.sh), because hook processes are spawned
by the agent with the agent's environment, not by `wiki`.

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

ENGINE = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="bash + jq required for the dispatcher libs",
)


def _bash(script: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, check=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             **(env or {})},
    )
    return result.stdout


def _source(vault: str, extra_env: dict | None = None, tail: str = "") -> str:
    return _bash(
        f"WIKI_DIR='{vault}/.wiki' ROOT_DIR='{vault}'; "
        f"source '{ENGINE}/lib/common.sh'; {tail}",
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


@pytest.mark.parametrize("agent", ["claude", "codex", "gemini", "cursor"])
def test_hook_commands_carry_the_environment_for_cloud_vaults(agent):
    out = _source(
        ICLOUD_VAULT,
        tail=f"source '{ENGINE}/lib/agents.sh'; agent_payload {agent}",
    )
    payload = json.loads(out)
    commands = [
        h["command"]
        for group in payload["hooks"].values()
        for entry in group
        for h in (entry["hooks"] if "hooks" in entry else [entry])
    ]
    assert commands, f"{agent}: no hook commands emitted"
    for cmd in commands:
        assert cmd.startswith(f"cd '{ICLOUD_VAULT}/.wiki' && "), cmd
        assert "UV_PROJECT_ENVIRONMENT='/h/.venvs/lxw-wiki' uv run python hooks/" in cmd, cmd


def test_hook_commands_stay_plain_for_plain_vaults():
    out = _source(PLAIN_VAULT, tail=f"source '{ENGINE}/lib/agents.sh'; agent_payload claude")
    payload = json.loads(out)
    cmd = payload["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
    assert cmd == f"cd '{PLAIN_VAULT}/.wiki' && uv run python hooks/session-end.py"


def test_hooks_installed_regex_matches_env_form(tmp_path: Path):
    """`hooks_installed` (and health.check_hooks_installed, same grammar)
    must recognise the new command shape as a wiki-managed hook."""
    cfg = tmp_path / "hooks.json"
    cfg.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command":
        f"cd '{ICLOUD_VAULT}/.wiki' && UV_PROJECT_ENVIRONMENT='/h/.venvs/lxw-wiki' "
        "uv run python hooks/session-end.py"}]}]}}))
    out = _bash(
        f"WIKI_DIR='{ICLOUD_VAULT}/.wiki' ROOT_DIR='{ICLOUD_VAULT}'; "
        f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; "
        f"hooks_installed '{cfg}' && printf yes || printf no"
    )
    assert out == "yes"
