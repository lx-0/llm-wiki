"""Shared structural-lint computation for the dashboard renderers (C04).

`flush.py` refreshes the dashboard by spawning `dashboard_stats.py` and then
`dashboard_lint.py` as two subprocesses under one refresh lock. Both need the
same structural check results — before C04, stats re-ran 6 checks for a count
and lint re-ran 3 of them for lists, each check re-reading the whole corpus
(the documented 120s+ refresh tail).

Now the checks both surfaces consume run ONCE over a single `lint.LintContext`
(`compute_lint_results`). The stats run — first in the flush sequence —
persists the structured issues to ``STATE_DIR/dashboard-lint-results.json``;
the lint run consumes that cache while it is fresh (younger than
``limits.dashboard_refresh_timeout_s``, the per-script bound on the stats→lint
gap inside one refresh) and recomputes only when run standalone later.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import STATE_DIR  # noqa: E402
from core.utils import now_iso  # noqa: E402

CACHE_FILE = STATE_DIR / "dashboard-lint-results.json"

# Structural checks the dashboard surfaces consume: stats sums them for the
# `lint_warnings` count; the lint queues render `orphan_pages` + `stale_articles`.
DASHBOARD_CHECK_NAMES = (
    "broken_links",
    "orphan_pages",
    "orphan_sources",
    "stale_articles",
    "article_type",
)


@dataclass(frozen=True)
class LintResults:
    """Structural lint issues per check name, computed over ONE LintContext."""

    generated_at: str
    issues: dict[str, list]  # check name -> list[lint.Issue]

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.issues.values())

    def get(self, name: str) -> list:
        return self.issues.get(name, [])


def compute_lint_results() -> LintResults:
    """Build the LintContext once and run every dashboard-consumed check."""
    import lint

    ctx = lint.build_context()
    checks = {
        "broken_links": lint.check_broken_links,
        "orphan_pages": lint.check_orphan_pages,
        "orphan_sources": lint.check_orphan_sources,
        "stale_articles": lint.check_stale_articles,
        "article_type": lint.check_article_type,
    }
    issues: dict[str, list] = {}
    for name in DASHBOARD_CHECK_NAMES:
        try:
            issues[name] = checks[name](ctx)
        except Exception:  # noqa: BLE001 — one bad check must not sink the dashboard
            issues[name] = []
    return LintResults(generated_at=now_iso(), issues=issues)


def save_cache(results: LintResults) -> None:
    """Persist the structured results for the follow-up dashboard_lint run.

    Best-effort: the cache is an optimization, never the source of truth."""
    try:
        payload = {
            "generated_at": results.generated_at,
            "issues": {
                name: [asdict(i) for i in items]
                for name, items in results.issues.items()
            },
        }
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_fresh_cache(max_age_s: float) -> LintResults | None:
    """Load the persisted results if they are younger than ``max_age_s``.

    Returns None on missing/stale/corrupt cache — the caller recomputes."""
    import lint

    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(payload["generated_at"])
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - generated_at).total_seconds()
        if age < 0 or age > max_age_s:
            return None
        issues = {
            name: [lint.Issue(**item) for item in items]
            for name, items in payload["issues"].items()
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return LintResults(generated_at=payload["generated_at"], issues=issues)
