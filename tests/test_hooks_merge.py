"""lib/agents.sh `merge_into_config` — installing wiki hooks must not drop
the operator's other hooks in the same event.

jq's deep-merge (`*`) replaces arrays. Before 2026-09-17 a `wiki hooks
install` into a Claude settings.json whose SessionStart already held a
ytstack hook, or a Codex hooks.json with a herdr hook, would have left only
the wiki entry behind. Per event the merge now keeps every non-wiki entry
and replaces only the wiki-managed one(s).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
VAULT = "/h/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="bash + jq required",
)


def _merge(cfg: Path, agent: str) -> dict:
    subprocess.run(
        [
            "bash",
            "-c",
            f"WIKI_DIR='{VAULT}/.wiki' ROOT_DIR='{VAULT}'; "
            f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; "
            f"merge_into_config '{cfg}' \"$(agent_payload {agent})\"",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    return json.loads(cfg.read_text())


def _old_wiki(script: str) -> dict:
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "timeout": 10,
                "command": f"cd '{VAULT}/.wiki' && uv run python hooks/{script}",
            }
        ],
    }


def test_codex_merge_keeps_foreign_session_start_hook(tmp_path: Path):
    cfg = tmp_path / "hooks.json"
    herdr = {
        "hooks": [
            {
                "type": "command",
                "command": "bash '/h/.codex/herdr-agent-state.sh' session",
                "timeout": 10,
            }
        ]
    }
    cfg.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [_old_wiki("session-start.py"), herdr],
                    "Stop": [_old_wiki("session-end.py")],
                }
            }
        )
    )
    out = _merge(cfg, "codex")
    start = out["hooks"]["SessionStart"]
    assert herdr in start, "the operator's own hook must survive the install"
    wiki = [e for e in start if ".wiki" in json.dumps(e)]
    assert len(wiki) == 1, "exactly one wiki entry after re-install, not two"
    assert "UV_PROJECT_ENVIRONMENT='/h/.venvs/lxw-wiki'" in wiki[0]["hooks"][0]["command"]
    assert len(out["hooks"]["Stop"]) == 1


def test_claude_merge_preserves_other_top_level_keys_and_events(tmp_path: Path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(git status)"]},
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": "ytstack-inject"}]}],
                    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other"}]}],
                },
            }
        )
    )
    out = _merge(cfg, "claude")
    assert out["permissions"] == {"allow": ["Bash(git status)"]}
    assert out["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "other"
    start_cmds = [h["command"] for e in out["hooks"]["SessionStart"] for h in e["hooks"]]
    assert "ytstack-inject" in start_cmds
    assert any("hooks/session-start.py" in c for c in start_cmds)
    assert "SessionEnd" in out["hooks"] and "PreCompact" in out["hooks"]


def test_cursor_bare_entries_are_recognised(tmp_path: Path):
    cfg = tmp_path / "hooks.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "sessionStart": [
                        {
                            "type": "command",
                            "command": f"cd '{VAULT}/.wiki' && uv run python hooks/session-start.py",
                            "timeout": 15,
                        },
                        {"type": "command", "command": "my-own-hook", "timeout": 5},
                    ],
                },
            }
        )
    )
    out = _merge(cfg, "cursor")
    cmds = [e["command"] for e in out["hooks"]["sessionStart"]]
    assert "my-own-hook" in cmds
    assert sum("hooks/session-start.py" in c for c in cmds) == 1


def test_fresh_file_is_the_payload(tmp_path: Path):
    cfg = tmp_path / "new" / "hooks.json"
    out = _merge(cfg, "codex")
    assert set(out["hooks"]) == {"SessionStart", "Stop"}


def test_merge_is_idempotent(tmp_path: Path):
    cfg = tmp_path / "hooks.json"
    cfg.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep"}]}]}})
    )
    once = _merge(cfg, "codex")
    twice = _merge(cfg, "codex")
    assert once == twice
    assert len(twice["hooks"]["Stop"]) == 2


# ── backup_file ──────────────────────────────────────────────────────


def test_a_backup_never_replaces_one_from_the_same_second(tmp_path: Path):
    """Backups are named to the second. An install and an uninstall within one second took
    the same name, and the second copy replaced the first: the pre-install original."""
    frozen = tmp_path / "bin"
    frozen.mkdir()
    (frozen / "date").write_text("#!/bin/sh\necho 20261015-120000\n", encoding="utf-8")
    (frozen / "date").chmod(0o755)
    cfg = tmp_path / "settings.json"
    run = subprocess.run(
        [
            "bash",
            "-c",
            f"WIKI_DIR='{VAULT}/.wiki' ROOT_DIR='{VAULT}'; source '{ENGINE}/lib/common.sh'; "
            'echo original > "$CFG"; backup_file "$CFG"; echo; '
            'echo installed > "$CFG"; backup_file "$CFG"',
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"CFG": str(cfg), "HOME": "/h", "PATH": f"{frozen}:/usr/bin:/bin"},
    )
    first, second = run.stdout.splitlines()
    assert first == f"{cfg}.bak.20261015-120000"
    assert second == f"{cfg}.bak.20261015-120000-2"
    assert Path(first).read_text() == "original\n"
    assert Path(second).read_text() == "installed\n"


# ── uninstall_one ────────────────────────────────────────────────────


def _uninstall(home: Path, agent: str, scope: str = "user") -> subprocess.CompletedProcess[str]:
    """`uninstall_one` with HOME (user scope) at ``home`` and the vault (project scope) at
    ``home/vault``."""
    return subprocess.run(
        [
            "bash",
            "-c",
            f"WIKI_DIR='{VAULT}/.wiki' ROOT_DIR=\"$HOME/vault\"; "
            f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; "
            f"uninstall_one {agent} {scope}",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


def test_uninstall_removes_todays_hooks_and_keeps_another_tools(tmp_path: Path):
    """The uninstall filtered on `.wiki/hooks/`, a drifted copy of the grammar: today's
    `cd '<vault>/.wiki' && uv run python hooks/…` stayed, and it reported success."""
    cfg = tmp_path / ".claude" / "settings.json"
    cfg.parent.mkdir()
    other = {"matcher": "", "hooks": [{"type": "command", "command": "ytstack-inject"}]}
    before = {"permissions": {"allow": ["Bash(ls:*)"]}, "hooks": {"SessionStart": [other]}}
    cfg.write_text(json.dumps(before))
    _merge(cfg, "claude")  # the wiki's three events, beside the other tool's hook

    run = _uninstall(tmp_path, "claude")

    assert run.returncode == 0, run.stderr
    assert json.loads(cfg.read_text()) == before
    assert "removed wiki hooks" in run.stdout


def test_uninstall_keeps_another_tools_bare_cursor_entry(tmp_path: Path):
    """Cursor's entries are bare `{type, command}`. The filter kept only entries carrying a
    `.hooks` array, so it dropped the operator's own Cursor hooks along with the wiki's."""
    cfg = tmp_path / "vault" / ".cursor" / "hooks.json"
    cfg.parent.mkdir(parents=True)
    mine = {"type": "command", "command": "my-own-hook", "timeout": 5}
    before = {"version": 1, "hooks": {"sessionStart": [mine]}}
    cfg.write_text(json.dumps(before))
    _merge(cfg, "cursor")

    run = _uninstall(tmp_path, "cursor", "project")

    assert run.returncode == 0, run.stderr
    assert json.loads(cfg.read_text()) == before


def test_uninstall_with_nothing_of_ours_leaves_the_file_alone(tmp_path: Path):
    cfg = tmp_path / ".claude" / "settings.json"
    cfg.parent.mkdir()
    text = json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "other"}]}]}})
    cfg.write_text(text)

    run = _uninstall(tmp_path, "claude")

    assert run.returncode == 0, run.stderr
    assert cfg.read_text() == text
    assert [p.name for p in cfg.parent.iterdir()] == ["settings.json"]  # no backup either
    assert "nothing to remove" in run.stdout


def test_uninstall_leaves_an_unreadable_config_as_it_was(tmp_path: Path):
    """jq failing on the file left a stray `.tmp` and still printed `removed wiki hooks`."""
    cfg = tmp_path / ".claude" / "settings.json"
    cfg.parent.mkdir()
    cfg.write_text("{ not json")

    run = _uninstall(tmp_path, "claude")

    assert run.returncode == 1
    assert cfg.read_text() == "{ not json"
    assert [p.name for p in cfg.parent.iterdir()] == ["settings.json"]  # no .tmp, no backup
    assert "could not read" in run.stderr
    assert "removed" not in run.stdout
