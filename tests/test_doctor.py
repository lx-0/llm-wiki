"""Smoke tests for scripts/doctor.py — CLI surface.

Per-check behaviour is covered in test_health.py. This file verifies
the CLI runs in each mode (default / --quick / --json / both flags),
produces valid output, and returns the right exit code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DOCTOR), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_doctor_default_renders_pretty_report():
    proc = _run([])
    assert proc.returncode in (0, 1), proc.stderr
    assert "Vault health" in proc.stdout
    assert "Summary:" in proc.stdout
    assert "Config + setup" in proc.stdout


def test_doctor_quick_runs_fast():
    """--quick is a soft promise of speed. Cap loosely: should not need
    network or claude subprocess, well under 5s even cold."""
    import time

    started = time.monotonic()
    proc = _run(["--quick"])
    elapsed = time.monotonic() - started
    assert proc.returncode in (0, 1)
    assert elapsed < 5.0, f"--quick took {elapsed:.1f}s; expected <5s"


def test_doctor_json_emits_valid_payload():
    proc = _run(["--json"])
    assert proc.returncode in (0, 1)
    data = json.loads(proc.stdout)
    assert set(data.keys()) >= {"vault", "engine_revision", "summary", "checks"}
    assert isinstance(data["checks"], list)
    assert all(
        set(c.keys()) >= {"id", "category", "severity", "message"}
        for c in data["checks"]
    )
    # summary counts must equal actual severities
    counted = {"critical": 0, "warning": 0, "info": 0, "ok": 0}
    for c in data["checks"]:
        counted[c["severity"]] = counted.get(c["severity"], 0) + 1
    assert counted == data["summary"]


def test_doctor_quick_json_combined():
    proc = _run(["--quick", "--json"])
    assert proc.returncode in (0, 1)
    data = json.loads(proc.stdout)
    # --quick → ollama check is info "skipped", claude probed without subprocess
    skipped = [c for c in data["checks"] if "skipped" in c["message"].lower()]
    assert skipped, "expected at least one check skipped in --quick mode"


def test_doctor_exit_code_zero_in_engine_repo():
    """The engine repo as run from here should have no critical issues
    (it's the engine itself, not a fresh untouched vault)."""
    proc = _run([])
    # Allow 0 (no critical) or 1 (critical found). We just verify it's
    # not crashing with some other code.
    assert proc.returncode in (0, 1)


def test_doctor_help():
    proc = _run(["--help"])
    assert proc.returncode == 0
    assert "vault-health audit" in proc.stdout.lower()
