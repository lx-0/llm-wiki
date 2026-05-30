"""Run a piggyback command with a hard wall-clock timeout and record its
outcome into ``piggyback-state.json``.

flush.py spawns piggybacks detached (fire-and-forget, stdout/stderr →
DEVNULL) so it can never observe whether the child succeeded, hung, or
crashed — ``status`` froze at ``"spawned"`` the instant ``Popen`` returned.
The review-wiki piggyback then sat on a half-open socket for 19h47m with no
surfaced evidence (incident 2026-05-30, see KNOWLEDGE.md "Ollama half-open
socket" + "silent piggyback").

This wrapper is spawned *instead of* the bare command::

    python core/piggyback_runner.py <name> <timeout_s> -- <cmd> [args...]

It records ``status`` running → ``ok`` | ``failed:<rc>`` | ``timeout`` |
``error:<Type>`` via a locked read-modify-write that only touches its own
``<name>`` key, so concurrent piggybacks don't clobber each other. On timeout
it kills the child's whole process group (covers grandchildren like ffmpeg /
whisper), which is the backstop that bounds the half-open-socket hang class
even if a collector forgets its own timeouts.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Make `core.*` importable when run as a script (Popen passes an absolute path
# with arbitrary CWD), mirroring the engine's other entrypoints.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import STATE_DIR  # noqa: E402

PIGGYBACK_STATE_FILE = STATE_DIR / "piggyback-state.json"

# Grace period between SIGTERM and SIGKILL when force-killing a timed-out
# child process group.
_TERM_GRACE_S = 3


def _now_iso() -> str:
    """Local-tz ISO timestamp, second precision — matches flush.py's format."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def record_status(
    name: str,
    fields: dict,
    *,
    state_file: Path = PIGGYBACK_STATE_FILE,
) -> None:
    """Merge ``fields`` into ``piggyback-state.json[name]`` under an exclusive
    lock.

    Read-modify-write so a concurrent writer (another piggyback runner, or
    flush.py recording the initial ``spawned`` state) never clobbers keys it
    didn't touch. The lock lives on a sibling ``*.lock`` file so we never
    truncate the data file while holding only a shared view of it.
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_file.with_name(state_file.name + ".lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            data: dict = {}
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
            entry = data.get(name)
            if not isinstance(entry, dict):
                entry = {}
            entry.update(fields)
            data[name] = entry
            state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _terminate(proc: subprocess.Popen) -> None:
    """Best-effort kill of a timed-out child and its descendants.

    The child is spawned with ``start_new_session=True`` so it leads its own
    process group; a group SIGTERM→SIGKILL reaps grandchildren (ffmpeg /
    whisper / spawned SDK CLIs) that a bare ``proc.kill()`` would orphan. But
    group signalling can be denied (EPERM) in restricted sandboxes and the
    group may already be gone (ESRCH) — both are swallowed, and we always
    fall back to killing the direct child so a timeout is never leaked.
    """
    if sys.platform == "win32":
        proc.kill()
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(_TERM_GRACE_S)
        if proc.poll() is None:
            os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass  # EPERM / ESRCH — fall through to the direct-child kill below
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


def run_piggyback(
    name: str,
    timeout_s: int,
    cmd: list[str],
    *,
    state_file: Path = PIGGYBACK_STATE_FILE,
) -> int:
    """Run ``cmd`` with a hard ``timeout_s`` cap, recording outcome to state.

    Returns the child's exit code, or 124 on timeout (conventional), or 1 on
    spawn/wait error. ``timeout_s <= 0`` disables the cap (runs unbounded —
    use only when a task self-bounds).
    """
    started = time.time()
    record_status(name, {"status": "running", "started": _now_iso()}, state_file=state_file)

    try:
        proc = subprocess.Popen(  # noqa: S603 — cmd is engine-constructed, not user input
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(sys.platform != "win32"),
        )
    except Exception as exc:  # noqa: BLE001 — record any spawn failure
        record_status(
            name,
            {
                "status": f"error:{type(exc).__name__}",
                "ended": _now_iso(),
                "duration_s": round(time.time() - started, 1),
                "last_error": str(exc)[:300],
            },
            state_file=state_file,
        )
        return 1

    record_status(name, {"pid": proc.pid}, state_file=state_file)

    wait_timeout = timeout_s if timeout_s and timeout_s > 0 else None
    try:
        rc = proc.wait(timeout=wait_timeout)
    except subprocess.TimeoutExpired:
        _terminate(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        record_status(
            name,
            {
                "status": "timeout",
                "ended": _now_iso(),
                "duration_s": round(time.time() - started, 1),
                "last_error": f"killed after {timeout_s}s wall-clock cap",
            },
            state_file=state_file,
        )
        return 124

    duration = round(time.time() - started, 1)
    status = "ok" if rc == 0 else f"failed:{rc}"
    record_status(
        name,
        {"status": status, "ended": _now_iso(), "duration_s": duration},
        state_file=state_file,
    )
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("name", help="piggyback task name (key in piggyback-state.json)")
    parser.add_argument("timeout_s", type=int, help="hard wall-clock cap in seconds (<=0 disables)")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="-- followed by the command to run")
    args = parser.parse_args(argv)

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("no command given after `--`")

    return run_piggyback(args.name, args.timeout_s, cmd)


if __name__ == "__main__":
    sys.exit(main())
