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
