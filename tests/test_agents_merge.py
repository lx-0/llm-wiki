"""`core.agents.merge` / `without_wiki_hooks` (M034-S03-T04) — the bash's `merge_into_config`
and `uninstall_one` as pure functions, held to the file text the bash wrote.

The bash's output for every fixture was recorded under tests/golden/agents/ before
lib/agents.sh was deleted (M034-S03-T07; recorded from the bash itself, the uninstall inputs
being the bash's own merges). Python must write those texts: an install writes operators'
agent configs, and a reinstall must not change a byte the bash would not have changed. An
intended change re-records with `--snapshot-update` and says why in its commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import agents

from ._oracle import assert_matches_golden

GOLDEN = Path(__file__).resolve().parent / "golden" / "agents"
VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
VENV = "/h/.venvs/lxw-wiki"  # the cloud rule's environment for VAULT under HOME=/h


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

# an empty group or event that was empty before stays; only the removal's empties go
EMPTIED: dict[str, tuple[str, dict]] = {
    "an-empty-group-stays": (
        "claude",
        {"hooks": {"SessionStart": [{"matcher": "", "hooks": []}, _old_wiki("session-start.py")]}},
    ),
    "an-empty-event-stays": (
        "claude",
        {"hooks": {"SessionStart": [], "Stop": [_old_wiki("session-end.py")]}},
    ),
}


def _payload(agent: str) -> dict:
    return agents.payload(agent, wiki_dir=Path(VAULT) / ".wiki", venv=VENV)


@pytest.mark.parametrize("name", sorted(MERGES))
def test_merge_writes_what_the_bash_wrote(request: pytest.FixtureRequest, name: str) -> None:
    agent, before = MERGES[name]
    text = agents.render(agents.merge(before, _payload(agent)))
    assert_matches_golden(request, f"merge-{name}.json", text, GOLDEN)


@pytest.mark.parametrize("name", sorted(MERGES))
def test_a_second_merge_changes_nothing(name: str) -> None:
    agent, before = MERGES[name]
    once = agents.merge(before, _payload(agent))
    assert agents.render(agents.merge(once, _payload(agent))) == agents.render(once)


@pytest.mark.parametrize("name", sorted(MERGES))
def test_uninstall_after_a_merge_writes_what_the_bash_wrote(
    request: pytest.FixtureRequest, name: str
) -> None:
    installed = json.loads((GOLDEN / f"merge-{name}.json").read_text(encoding="utf-8"))
    text = agents.render(agents.without_wiki_hooks(installed))
    assert_matches_golden(request, f"uninstall-{name}.json", text, GOLDEN)


@pytest.mark.parametrize("name", sorted(EMPTIED))
def test_uninstall_drops_only_what_the_removal_emptied(
    request: pytest.FixtureRequest, name: str
) -> None:
    _agent, config = EMPTIED[name]
    text = agents.render(agents.without_wiki_hooks(config))
    assert_matches_golden(request, f"uninstall-{name}.json", text, GOLDEN)


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
