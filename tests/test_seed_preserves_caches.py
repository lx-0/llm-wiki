"""Regression test for M003-S07-T01: `wiki seed --force` must NOT touch
`_dashboard-stats.md` (cache files are producer-only outputs, not templates).

Reproduces the lxw bug: live cache with real counts gets bytegenau replaced
by the placeholder template after `wiki seed --force` ran. Lock that down.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = REPO_ROOT / "lib"
TEMPLATE_FILE = REPO_ROOT / "templates" / "_dashboard-stats.md"

LIVE_CACHE_CONTENT = """\
---
pending_compiles: 303
failed_flushes: 1
lint_warnings: 2351
total_cost_lifetime: 7.2486
articles_total: 470
daily_logs_total: 19
last_compile_ts: 2026-05-02T19:52:55+00:00
generated_at: 2026-05-02T21:52:59+02:00
---

> [!info] Pipeline status
> 🟢 **Pending compiles:** 303
"""


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def test_seed_force_does_not_clobber_live_dashboard_stats(tmp_path: Path) -> None:
    """seed_vault_templates with force=1 must leave a populated cache file untouched."""
    # Build minimal wiki_dir + target layout.
    wiki_dir = tmp_path / "wiki"
    target = tmp_path / "vault"
    (wiki_dir / "templates").mkdir(parents=True)
    target.mkdir()

    # Seed templates dir with the actual placeholder + the two other templates
    # `_seed_file` will iterate.
    shutil.copy(TEMPLATE_FILE, wiki_dir / "templates" / "_dashboard-stats.md")
    (wiki_dir / "templates" / "AGENTS.example.md").write_text("AGENTS placeholder", encoding="utf-8")
    (wiki_dir / "templates" / "dashboard.md").write_text("# Dashboard placeholder", encoding="utf-8")

    # Live cache with real counts.
    cache = target / "_dashboard-stats.md"
    cache.write_text(LIVE_CACHE_CONTENT, encoding="utf-8")
    cache_md5_before = _md5(cache)

    # Source common.sh + seed.sh, invoke seed_vault_templates with force=1.
    script = f"""
set -euo pipefail
export WIKI_DIR="{wiki_dir}"
export ROOT_DIR="{target}"
source "{LIB_DIR}/common.sh"
source "{LIB_DIR}/seed.sh"
seed_vault_templates "{target}" "{wiki_dir}" 1
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Seed itself must succeed (not a test of failure, of preservation).
    assert result.returncode == 0, f"seed failed: {result.stderr}"

    # The cache file must NOT have been touched.
    cache_md5_after = _md5(cache)
    assert cache_md5_after == cache_md5_before, (
        f"cache was clobbered. Stdout: {result.stdout}\nStderr: {result.stderr}"
    )

    # And content must still be the live counts.
    after_content = cache.read_text(encoding="utf-8")
    assert "pending_compiles: 303" in after_content
    assert "Placeholder" not in after_content
