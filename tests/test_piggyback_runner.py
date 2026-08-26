"""piggyback_runner records each task's real outcome and enforces a hard
wall-clock cap — the backstop that bounds the silent-hang class (review-wiki
ran 19h47m as status="spawned" with no surfaced evidence, 2026-05-30)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_records_ok(tmp_path):
    from core import piggyback_runner as pr
    sf = tmp_path / "piggyback-state.json"
    rc = pr.run_piggyback("t", 60, [sys.executable, "-c", "pass"], state_file=sf)
    assert rc == 0
    entry = json.loads(sf.read_text())["t"]
    assert entry["status"] == "ok"
    assert "duration_s" in entry and "ended" in entry and "pid" in entry


def test_records_nonzero_exit(tmp_path):
    from core import piggyback_runner as pr
    sf = tmp_path / "piggyback-state.json"
    rc = pr.run_piggyback("t", 60, [sys.executable, "-c", "import sys; sys.exit(3)"], state_file=sf)
    assert rc == 3
    assert json.loads(sf.read_text())["t"]["status"] == "failed:3"


def test_stale_last_error_is_overwritten_on_next_run(tmp_path):
    """Live incident (audit 2026-08-25): review-wiki showed a day-old
    "killed after 14400s" last_error for an 8.5 s rc=1 run — the rc-path
    merged without touching last_error. Every completed run must overwrite
    it: fresh text on failure, None on success."""
    from core import piggyback_runner as pr
    sf = tmp_path / "piggyback-state.json"
    sf.write_text(json.dumps({"t": {"last_error": "killed after 14400s wall-clock cap"}}))

    pr.run_piggyback("t", 60, [sys.executable, "-c", "import sys; sys.exit(1)"], state_file=sf)
    entry = json.loads(sf.read_text())["t"]
    assert entry["last_error"] == "exit 1"

    pr.run_piggyback("t", 60, [sys.executable, "-c", "pass"], state_file=sf)
    entry = json.loads(sf.read_text())["t"]
    assert entry["status"] == "ok" and entry["last_error"] is None


def test_killed_runner_records_interrupted_not_running(tmp_path):
    """A runner that is itself killed must not leave `status=running` behind.

    Observed twice on 2026-08-26: a foreground timeout killed the runner
    mid-child, and piggyback-state.json kept `status: running` with a dead pid
    forever. Doctor's orphan check only notices after the wall-clock cap + 1 h,
    so until then the entry silently lies about a task that is not running —
    and the previous real outcome is buried. On SIGTERM/SIGINT the runner
    records `interrupted`, reaps its child, and exits.
    """
    import signal
    import subprocess as sp

    from core import piggyback_runner as pr

    sf = tmp_path / "piggyback-state.json"
    scripts_dir = Path(pr.__file__).resolve().parent.parent
    driver = (
        "import sys; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from core import piggyback_runner as pr\n"
        "pr.run_piggyback('t', 600, [%r, '-c', 'import time; time.sleep(60)'],"
        " state_file=Path(%r))\n" % (str(scripts_dir), sys.executable, str(sf))
    )
    proc = sp.Popen([sys.executable, "-c", driver],
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    # Wait for the runner to record `running` before signalling it.
    for _ in range(100):
        if sf.exists() and json.loads(sf.read_text()).get("t", {}).get("status") == "running":
            break
        time.sleep(0.05)
    else:
        proc.kill()
        raise AssertionError("runner never recorded `running`")

    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=15)

    entry = json.loads(sf.read_text())["t"]
    assert entry["status"] == "interrupted", entry
    assert entry["last_error"]
    assert "ended" in entry and "duration_s" in entry


def test_records_timeout_and_kills_promptly(tmp_path):
    from core import piggyback_runner as pr
    sf = tmp_path / "piggyback-state.json"
    start = time.time()
    rc = pr.run_piggyback(
        "t", 1, [sys.executable, "-c", "import time; time.sleep(30)"], state_file=sf
    )
    elapsed = time.time() - start
    assert rc == 124
    assert json.loads(sf.read_text())["t"]["status"] == "timeout"
    # Killed at ~1s cap + TERM grace — must NOT wait the full 30s sleep.
    assert elapsed < 12, f"timeout kill took {elapsed:.1f}s — process-group kill ineffective"


def test_rmw_preserves_other_keys(tmp_path):
    """The locked read-modify-write must touch only its own key, so a
    concurrent writer (another runner, or flush recording 'spawned') keeps its
    data and the cooldown anchor (last_run) survives."""
    from core import piggyback_runner as pr
    sf = tmp_path / "piggyback-state.json"
    sf.write_text(json.dumps({
        "other": {"last_run": "2026-01-01T00:00:00", "status": "ok"},
        "t": {"last_run": "KEEP-ME"},
    }))
    pr.run_piggyback("t", 60, [sys.executable, "-c", "pass"], state_file=sf)
    data = json.loads(sf.read_text())
    assert data["other"] == {"last_run": "2026-01-01T00:00:00", "status": "ok"}
    assert data["t"]["last_run"] == "KEEP-ME"   # cooldown anchor preserved
    assert data["t"]["status"] == "ok"
