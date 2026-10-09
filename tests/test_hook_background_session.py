"""The hook's actual spawn policy gives flush a distinct POSIX session."""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-session contract")
@pytest.mark.parametrize("hook_name", ["session-end", "pre-compact"])
def test_staged_flush_is_spawned_in_independent_session(tmp_path, monkeypatch, hook_name):
    hooks = Path(__file__).resolve().parent.parent / "hooks"
    monkeypatch.syspath_prepend(str(hooks))
    spec = importlib.util.spec_from_file_location(f"test_{hook_name}", hooks / f"{hook_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("CLAUDE_INVOKED_BY", raising=False)
    monkeypatch.setattr(module.sys, "stdin", io.StringIO(json.dumps({
        "session_id": "thread-123", "turn_id": "turn-456",
        "transcript_path": str(tmp_path / "rollout.jsonl"),
    })))
    from _transcript import Turn
    monkeypatch.setattr(module, "read_transcript", lambda *args: [
        Turn(role="user", text=f"Remember item {i}") for i in range(5)
    ])
    staged = []

    def stage(kind, identity, context):
        staged.append((kind, identity, context))
        return SimpleNamespace(path=tmp_path / "staged.md")

    monkeypatch.setattr(module.flush_pipeline, "stage", stage)
    real_popen = subprocess.Popen
    children = []

    def spawn(cmd, **kwargs):
        assert cmd[-1] == "thread-123", "preserve session-level dedup and daily replacement"
        kwargs["stdout"] = subprocess.PIPE
        child = real_popen([sys.executable, "-c",
                           "import os; print(os.getpid(), os.getsid(0))"], **kwargs)
        out, _ = child.communicate(timeout=5)
        pid, sid = map(int, out.split())
        assert child.returncode == 0
        assert pid == sid and sid != os.getsid(0)
        children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    module.main()
    assert len(children) == 1
    assert staged[0][:2] == (hook_name, "thread-123")
