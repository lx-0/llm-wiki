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
        ["bash", "-c",
         f"WIKI_DIR='{VAULT}/.wiki' ROOT_DIR='{VAULT}'; "
         f"source '{ENGINE}/lib/common.sh'; source '{ENGINE}/lib/agents.sh'; "
         f"merge_into_config '{cfg}' \"$(agent_payload {agent})\""],
        check=True, capture_output=True, text=True,
        env={"HOME": "/h", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    return json.loads(cfg.read_text())


def _old_wiki(script: str) -> dict:
    return {"matcher": "", "hooks": [{"type": "command", "timeout": 10,
            "command": f"cd '{VAULT}/.wiki' && uv run python hooks/{script}"}]}


def test_codex_merge_keeps_foreign_session_start_hook(tmp_path: Path):
    cfg = tmp_path / "hooks.json"
    herdr = {"hooks": [{"type": "command", "command": "bash '/h/.codex/herdr-agent-state.sh' session", "timeout": 10}]}
    cfg.write_text(json.dumps({"hooks": {
        "SessionStart": [_old_wiki("session-start.py"), herdr],
        "Stop": [_old_wiki("session-end.py")],
    }}))
    out = _merge(cfg, "codex")
    start = out["hooks"]["SessionStart"]
    assert herdr in start, "the operator's own hook must survive the install"
    wiki = [e for e in start if ".wiki" in json.dumps(e)]
    assert len(wiki) == 1, "exactly one wiki entry after re-install, not two"
    assert "UV_PROJECT_ENVIRONMENT='/h/.venvs/lxw-wiki'" in wiki[0]["hooks"][0]["command"]
    assert len(out["hooks"]["Stop"]) == 1


def test_claude_merge_preserves_other_top_level_keys_and_events(tmp_path: Path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({
        "permissions": {"allow": ["Bash(git status)"]},
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "ytstack-inject"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other"}]}],
        },
    }))
    out = _merge(cfg, "claude")
    assert out["permissions"] == {"allow": ["Bash(git status)"]}
    assert out["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "other"
    start_cmds = [h["command"] for e in out["hooks"]["SessionStart"] for h in e["hooks"]]
    assert "ytstack-inject" in start_cmds
    assert any("hooks/session-start.py" in c for c in start_cmds)
    assert "SessionEnd" in out["hooks"] and "PreCompact" in out["hooks"]


def test_cursor_bare_entries_are_recognised(tmp_path: Path):
    cfg = tmp_path / "hooks.json"
    cfg.write_text(json.dumps({"version": 1, "hooks": {
        "sessionStart": [
            {"type": "command", "command": f"cd '{VAULT}/.wiki' && uv run python hooks/session-start.py", "timeout": 15},
            {"type": "command", "command": "my-own-hook", "timeout": 5},
        ],
    }}))
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
    cfg.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep"}]}]}}))
    once = _merge(cfg, "codex")
    twice = _merge(cfg, "codex")
    assert once == twice
    assert len(twice["hooks"]["Stop"]) == 2
