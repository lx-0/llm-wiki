"""`core.agents.merge` / `without_wiki_hooks` (M034-S03-T04) — the bash's `merge_into_config`
and `uninstall_one` as pure functions, held to the file text the bash writes.

Each fixture goes through the bash (sourced as in test_hooks_merge.py) and through Python, and
the two texts must be identical: the port (T05) writes operators' agent configs, and a
reinstall must not change a byte the bash would not have changed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import agents

ENGINE = Path(__file__).resolve().parent.parent
VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
VENV = "/h/.venvs/lxw-wiki"  # the bash's cloud rule for VAULT under HOME=/h

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None, reason="bash + jq required"
)


def _bash(root: Path, command: str, **env: str) -> None:
    subprocess.run(
        [
            "bash",
            "-c",
            f"WIKI_DIR='{VAULT}/.wiki' ROOT_DIR=\"$ROOT\"; "
            f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; {command}",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
        | {"ROOT": str(root), **env},
    )


def _old_wiki(script: str) -> dict:
    command = f"cd '{VAULT}/.wiki' && uv run python hooks/{script}"
    return {"matcher": "", "hooks": [{"type": "command", "timeout": 10, "command": command}]}


HERDR = {"hooks": [{"type": "command", "command": "bash '/h/.codex/herdr.sh' session"}]}
CURSOR_OURS = {
    "type": "command",
    "command": f"cd '{VAULT}/.wiki' && uv run python hooks/session-start.py",
    "timeout": 15,
}
MINE = {"type": "command", "command": "my-own-hook", "timeout": 5}

# name → (agent, the config before the install)
MERGES: dict[str, tuple[str, dict]] = {
    "claude-beside-another-tool": (
        "claude",
        {
            "permissions": {"allow": ["Bash(git status)"]},
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "ytstack-inject"}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other"}]}],
            },
        },
    ),
    "codex-herdr-and-an-older-wiki-entry": (
        "codex",
        {
            "hooks": {
                "SessionStart": [_old_wiki("session-start.py"), HERDR],
                "Stop": [_old_wiki("session-end.py")],
            }
        },
    ),
    "cursor-bare-entries": (
        "cursor",
        {"version": 1, "hooks": {"sessionStart": [CURSOR_OURS, MINE]}},
    ),
    "hooks-in-the-middle": (
        "claude",
        {"a": 1, "hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}, "z": {"n": {"x": 1}}},
    ),
    "top-level-deep-merge": ("cursor", {"version": 0, "extra": {"k": [1, 2]}, "hooks": None}),
    "non-ascii": ("gemini", {"ui": {"theme": "Größe ✓ 日本"}, "hooks": {}}),
    "no-hooks-yet": ("gemini", {"general": {"vimMode": True}}),
}


def _bash_merge(tmp_path: Path, agent: str, before: dict) -> str:
    cfg = tmp_path / "bash" / "settings.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(before), encoding="utf-8")
    # ROOT_DIR is the vault here: the bash names the cloud environment after its basename
    _bash(Path(VAULT), f'merge_into_config "$CFG" "$(agent_payload {agent})"', CFG=str(cfg))
    return cfg.read_text(encoding="utf-8")


def _payload(agent: str) -> dict:
    return agents.payload(agent, wiki_dir=Path(VAULT) / ".wiki", venv=VENV)


@pytest.mark.parametrize("name", sorted(MERGES))
def test_merge_writes_what_the_bash_writes(tmp_path: Path, name: str) -> None:
    agent, before = MERGES[name]
    assert agents.render(agents.merge(before, _payload(agent))) == _bash_merge(
        tmp_path, agent, before
    )


@pytest.mark.parametrize("name", sorted(MERGES))
def test_a_second_merge_changes_nothing(name: str) -> None:
    agent, before = MERGES[name]
    once = agents.merge(before, _payload(agent))
    assert agents.render(agents.merge(once, _payload(agent))) == agents.render(once)


def _bash_uninstall(tmp_path: Path, agent: str, before: dict) -> str:
    cfg = tmp_path / agents.agent(agent).config
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(before), encoding="utf-8")
    _bash(tmp_path, f"uninstall_one {agent} project")
    return cfg.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(MERGES))
def test_uninstall_after_a_merge_writes_what_the_bash_writes(tmp_path: Path, name: str) -> None:
    agent, before = MERGES[name]
    installed = agents.merge(before, _payload(agent))
    expected = _bash_uninstall(tmp_path, agent, installed)
    assert agents.render(agents.without_wiki_hooks(installed)) == expected


@pytest.mark.parametrize(
    ("agent", "config"),
    [
        # an empty group that was empty before stays; only the removal's empties go
        (
            "claude",
            {
                "hooks": {
                    "SessionStart": [{"matcher": "", "hooks": []}, _old_wiki("session-start.py")]
                }
            },
        ),
        ("claude", {"hooks": {"SessionStart": [], "Stop": [_old_wiki("session-end.py")]}}),
    ],
)
def test_uninstall_drops_only_what_the_removal_emptied(
    tmp_path: Path, agent: str, config: dict
) -> None:
    expected = _bash_uninstall(tmp_path, agent, config)
    assert agents.render(agents.without_wiki_hooks(config)) == expected


@pytest.mark.parametrize(
    "config",
    [
        {"hooks": {"SessionStart": [{"hooks": [{"command": "other"}]}]}},
        {"hooks": [1, 2]},
        {"permissions": {}},
    ],
)
def test_nothing_of_ours_comes_back_unchanged(config: dict) -> None:
    assert agents.without_wiki_hooks(config) == config
