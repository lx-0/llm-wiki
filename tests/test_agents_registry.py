"""`core/agents.py` (M034-S03-T01) — the agent registry in Python, held byte for byte to the
bash `lib/agents.sh` it replaced in M034-S03.

The payloads are compared as the files they become, not as parsed JSON: the installed hook
commands must not change on reinstall (M034 locked decision). The bash's `agent_payload |
jq .` for each agent and vault shape was recorded under tests/golden/agents/ before
lib/agents.sh was deleted (M034-S03-T07). A new agent records its own (`--snapshot-update`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core import agents

from ._oracle import assert_matches_golden

ENGINE = Path(__file__).resolve().parent.parent
GOLDEN = ENGINE / "tests" / "golden" / "agents"
# a cloud-synced vault whose path holds spaces: the iCloud rule puts the venv at
# $HOME/.venvs/<vault>-wiki, and the hook commands carry it literally
CLOUD_VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
# …and one whose name holds an apostrophe, written as '\'' inside the quotes (0.7.15)
APOSTROPHE_VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/Alex's Vault"
PLAIN_VAULT = "/srv/vaults/notes"


@pytest.mark.parametrize("agent", [a.name for a in agents.AGENTS])
@pytest.mark.parametrize(
    ("label", "vault", "venv"),
    [
        ("plain", PLAIN_VAULT, None),
        ("icloud", CLOUD_VAULT, "/h/.venvs/lxw-wiki"),
        ("apostrophe", APOSTROPHE_VAULT, "/h/.venvs/Alex's Vault-wiki"),
    ],
)
def test_payload_text_is_the_recorded_bash_output(request, agent, label, vault, venv):
    payload = agents.payload(agent, wiki_dir=Path(vault) / ".wiki", venv=venv)
    assert_matches_golden(request, f"payload-{agent}-{label}.json", agents.render(payload), GOLDEN)


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


@pytest.mark.parametrize(
    ("command", "ours"),
    # the bash probe's answers, held while lib/agents.sh existed (M034-S03-T01 … T06)
    [
        ("cd '/v/.wiki' && uv run python hooks/session-start.py", True),  # today's format
        ("cd '/v/.wiki' && UV_PROJECT_ENVIRONMENT='/e' uv run python hooks/pre-compact.py", True),
        ("uv run --project .wiki python .wiki/hooks/session-end.py", True),  # an older format
        ('cd "/v/.wiki" && uv run python hooks/_transcript.py', True),
        ("other-tool --start", False),  # foreign
        ("uv run python hooks/session-start.py", False),  # no .wiki path: not ours
        ("cd '/v/.wikipedia' && run hooks/session-start.py", False),  # .wiki is a prefix only
    ],
)
def test_one_grammar_for_a_wiki_hook_command(command, ours):
    assert agents.is_wiki_hook(command) is ours


OURS = "cd '/v/.wiki' && uv run python hooks/session-start.py"


def _claude(command: str) -> dict:
    hook = {"type": "command", "command": command}
    return {"hooks": {"SessionStart": [{"matcher": "", "hooks": [hook]}]}}


def test_the_probe_counts_hook_entries_not_text(tmp_path):
    """M034-S03-T05: `hooks status` and doctor walk the hook entries, as the merge and the
    uninstall decide. The bash grepped the file's text."""
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(_claude(OURS)), encoding="utf-8")
    assert agents.hooks_installed(cfg) is True
    # a permission rule naming the command is not a hook
    cfg.write_text(json.dumps({"permissions": {"allow": [f"Bash({OURS})"]}}), encoding="utf-8")
    assert agents.hooks_installed(cfg) is False
    # a double-quoted path, escaped as \" in the file, is one
    quoted = 'cd "/v/.wiki" && uv run python hooks/session-end.py'
    cfg.write_text(json.dumps(_claude(quoted)), encoding="utf-8")
    assert agents.hooks_installed(cfg) is True
    # Cursor's bare entries
    bare = {"version": 1, "hooks": {"sessionEnd": [{"type": "command", "command": OURS}]}}
    cfg.write_text(json.dumps(bare), encoding="utf-8")
    assert agents.hooks_installed(cfg) is True


def test_an_unreadable_or_missing_config_is_not_installed(tmp_path):
    cfg = tmp_path / "settings.json"
    assert agents.read_config(cfg) is None
    assert agents.hooks_installed(cfg) is False
    cfg.write_text(json.dumps(_claude(OURS))[:-3], encoding="utf-8")  # cut off mid-write
    with pytest.raises(ValueError):
        agents.read_config(cfg)
    assert agents.hooks_installed(cfg) is False
    cfg.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        agents.read_config(cfg)


def test_wiki_commands_lists_only_ours():
    config = {
        "hooks": {
            "SessionStart": [{"hooks": [{"command": "other"}, {"command": OURS}]}],
            "Stop": "not a list",
        },
        "permissions": {"allow": [f"Bash({OURS})"]},
    }
    assert agents.wiki_commands(config) == [OURS]
    assert agents.wiki_commands({"hooks": [OURS]}) == []


def test_no_second_copy_of_the_grammar_outside_the_seam():
    """The bash carried three copies of the grammar and the doctor a fourth, each free to
    drift (the uninstall's matched nothing current). A new copy fails here, in the bash as
    well: 0.7.27's update warning put a fifth into `wiki`, where this test did not look."""
    copy = re.compile(r"hooks/\(session-")
    seam = ENGINE / "scripts" / "core" / "agents.py"
    engine_files = [
        *(path for tree in ("scripts", "hooks") for path in sorted((ENGINE / tree).rglob("*.py"))),
        ENGINE / "wiki",
        ENGINE / "install.sh",
        *sorted((ENGINE / "lib").glob("*.sh")),
    ]
    offenders = [
        str(path.relative_to(ENGINE))
        for path in engine_files
        if path != seam and copy.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_installed_wiki_commands_per_agent_and_scope(tmp_path):
    """One walker behind `wiki doctor` and `wiki update` (M034-S05-T02): the wiki hook
    commands each agent config holds, per scope, in registry × scope order. A config without
    any, and one that cannot be read, are left out."""
    home, root = tmp_path / "home", tmp_path / "vault"
    bare = "uv run --project .wiki python .wiki/hooks/session-end.py"
    configs = {
        home / ".claude" / "settings.json": json.dumps(_claude(OURS)),
        root / ".cursor" / "hooks.json": json.dumps(
            {"version": 1, "hooks": {"sessionEnd": [{"command": bare}]}}
        ),
        home / ".codex" / "hooks.json": "{",  # half written
        root / ".gemini" / "settings.json": json.dumps({"hooks": {}}),
        root / ".claude" / "settings.json": json.dumps({"permissions": {"allow": [OURS]}}),
    }
    for path, text in configs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    installed = agents.installed_wiki_commands(home=home, root=root)

    assert installed == {("claude", "user"): [OURS], ("cursor", "project"): [bare]}
    assert list(installed) == [("claude", "user"), ("cursor", "project")]


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
