"""Contract tests for generated multi-agent hook payloads."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


def test_codex_payload_uses_turn_scoped_stop_hook(tmp_path: Path):
    repo = Path(__file__).resolve().parent.parent
    agents_script = repo / "lib" / "agents.sh"
    wiki_dir = tmp_path / "vault" / ".wiki"
    shell = "\n".join(
        [
            "set -euo pipefail",
            f"WIKI_DIR={shlex.quote(str(wiki_dir))}",
            f"source {shlex.quote(str(agents_script))}",
            "codex_hooks_payload",
        ]
    )

    result = subprocess.run(
        ["bash", "-c", shell],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert set(payload["hooks"]) == {"SessionStart", "Stop"}
    start_command = payload["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    stop_command = payload["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "session-start.py" in start_command
    assert "session-end.py" in stop_command
    assert str(wiki_dir) in start_command
    assert str(wiki_dir) in stop_command
