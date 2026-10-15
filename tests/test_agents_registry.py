"""`core/agents.py` (M034-S03-T01) — the agent registry in Python, held byte for byte to the
bash `lib/agents.sh` it replaces in S03-T03.

The parity tests run the bash itself (`agent_payload`, `hooks_installed`) and compare text:
the installed hook commands must not change on reinstall (M034 locked decision), so the
payloads are compared as the files they become, not as parsed JSON.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core import agents

ENGINE = Path(__file__).resolve().parent.parent
# a cloud-synced vault whose path holds spaces: the bash's iCloud rule puts the venv at
# $HOME/.venvs/<vault>-wiki, and the hook commands carry it literally
CLOUD_VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
# …and one whose name holds an apostrophe, written as '\'' inside the quotes (0.7.15)
APOSTROPHE_VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/Alex's Vault"
PLAIN_VAULT = "/srv/vaults/notes"

needs_bash_jq = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None, reason="bash + jq required"
)


def _bash(vault: str, command: str, **env: str) -> str:
    script = (
        'WIKI_DIR="$V/.wiki" ROOT_DIR="$V"; '
        f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; {command}"
    )
    return subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "V": vault}
        | env,
    ).stdout


@needs_bash_jq
@pytest.mark.parametrize("agent", [a.name for a in agents.AGENTS])  # a new one needs the bash too
@pytest.mark.parametrize(
    ("vault", "venv"),
    [
        (PLAIN_VAULT, None),
        (CLOUD_VAULT, "/h/.venvs/lxw-wiki"),
        (APOSTROPHE_VAULT, "/h/.venvs/Alex's Vault-wiki"),
    ],
)
def test_payload_text_is_the_bash_jq_output(agent, vault, venv):
    expected = _bash(vault, f"agent_payload {agent} | jq .")
    payload = agents.payload(agent, wiki_dir=Path(vault) / ".wiki", venv=venv)
    assert agents.render(payload) == expected


def test_hook_cmd_shape():
    assert agents.hook_cmd("hooks/session-end.py", wiki_dir=Path("/v/.wiki"), venv=None) == (
        "cd '/v/.wiki' && uv run python hooks/session-end.py"
    )
    assert agents.hook_cmd("hooks/session-end.py", wiki_dir=Path("/v/.wiki"), venv="/e") == (
        "cd '/v/.wiki' && UV_PROJECT_ENVIRONMENT='/e' uv run python hooks/session-end.py"
    )
    quoted = agents.hook_cmd("hooks/pre-compact.py", wiki_dir=Path("/v/A's/.wiki"), venv="/e/A's")
    assert quoted == (
        "cd '/v/A'\\''s/.wiki' && UV_PROJECT_ENVIRONMENT='/e/A'\\''s' "
        "uv run python hooks/pre-compact.py"
    )


@needs_bash_jq
@pytest.mark.parametrize(
    "command",
    [
        "cd '/v/.wiki' && uv run python hooks/session-start.py",  # today's format
        "cd '/v/.wiki' && UV_PROJECT_ENVIRONMENT='/e' uv run python hooks/pre-compact.py",
        "uv run --project .wiki python .wiki/hooks/session-end.py",  # an older format
        'cd "/v/.wiki" && uv run python hooks/_transcript.py',
        "other-tool --start",  # foreign
        "uv run python hooks/session-start.py",  # no .wiki path: not ours
        "cd '/v/.wikipedia' && run hooks/session-start.py",  # .wiki is a prefix only
    ],
)
def test_one_grammar_matches_what_the_bash_probe_matches(tmp_path, command):
    cfg = tmp_path / "settings.json"
    cfg.write_text(f'{{"command": "{command}"}}\n', encoding="utf-8")
    probe = 'hooks_installed "$CFG" && echo yes || echo no'
    bash_says = _bash("/v", probe, CFG=str(cfg)).strip() == "yes"
    assert agents.hooks_installed(cfg) is bash_says
    assert agents.is_wiki_hook(command) is bash_says


def test_no_second_copy_of_the_grammar_outside_the_seam():
    """The bash carried three copies of the grammar and the doctor a fourth, each free to
    drift (the uninstall's matched nothing current). A new copy fails here."""
    copy = re.compile(r"hooks/\(session-")
    seam = ENGINE / "scripts" / "core" / "agents.py"
    offenders = [
        str(path.relative_to(ENGINE))
        for tree in ("scripts", "hooks")
        for path in sorted((ENGINE / tree).rglob("*.py"))
        if path != seam and copy.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_registry_paths(tmp_path):
    home, root = tmp_path / "home", tmp_path / "vault"
    (home / ".codex").mkdir(parents=True)
    assert [a.name for a in agents.AGENTS] == ["claude", "codex", "gemini", "cursor"]
    assert agents.config_path("gemini", "user", home=home, root=root) == (
        home / ".gemini" / "settings.json"
    )
    assert agents.config_path("cursor", "project", home=home, root=root) == (
        root / ".cursor" / "hooks.json"
    )
    assert agents.present("codex", "user", home=home, root=root) is True
    assert agents.present("claude", "user", home=home, root=root) is False
    with pytest.raises(KeyError):
        agents.config_path("pi", "user", home=home, root=root)
