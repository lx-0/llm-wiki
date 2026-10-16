"""Regression test for M003-S07-T01: `wiki seed --force` must NOT touch
`_dashboard-stats.md` (cache files are producer-only outputs, not templates).

Reproduces the lxw bug: live cache with real counts gets bytegenau replaced
by the placeholder template after `wiki seed --force` ran. Lock that down —
against the Python seed since M034-S04-T04 (`seed_cli.seed_vault`, the run
without the dashboards refresh that follows a writing run).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import seed_cli

REPO_ROOT = Path(__file__).resolve().parent.parent
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


def test_seed_force_does_not_clobber_live_dashboard_stats(tmp_path: Path, capsys) -> None:
    """seed with --force must leave a populated cache file untouched."""
    # Build minimal wiki_dir + target layout.
    wiki_dir = tmp_path / "wiki"
    target = tmp_path / "vault"
    (wiki_dir / "templates").mkdir(parents=True)
    (target / ".obsidian").mkdir(parents=True)

    # The templates dir holds the actual placeholder next to two templates the walk lists.
    shutil.copy(TEMPLATE_FILE, wiki_dir / "templates" / "_dashboard-stats.md")
    (wiki_dir / "templates" / "AGENTS.example.md").write_text(
        "AGENTS placeholder", encoding="utf-8"
    )
    (wiki_dir / "templates" / "dashboard.md").write_text(
        "# Dashboard placeholder", encoding="utf-8"
    )

    # Live cache with real counts.
    cache = target / "_dashboard-stats.md"
    cache.write_text(LIVE_CACHE_CONTENT, encoding="utf-8")
    cache_md5_before = _md5(cache)

    assert seed_cli.seed_vault(target, wiki_dir, force=True, check=False, only=None)
    out = capsys.readouterr().out
    assert "overwrote AGENTS.md (--force)" in out or "seeded AGENTS.md" in out

    # The cache file must NOT have been touched.
    assert _md5(cache) == cache_md5_before, f"cache was clobbered. Output: {out}"

    # And content must still be the live counts.
    after_content = cache.read_text(encoding="utf-8")
    assert "pending_compiles: 303" in after_content
    assert "Placeholder" not in after_content
