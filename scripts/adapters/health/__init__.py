"""Health-substrate adapters.

Phase 1 (2026-05-15): Oura only via REST + Bearer PAT. HealthKit XML
drop-folder (Phase 2) and Health Auto Export (Phase 3) deferred per
.ytstack/AD-HOC-health-phase-1-PLAN.md.
"""

from adapters.health.oura import (  # noqa: F401  re-export public API
    DailySummary,
    OuraAPIError,
    OuraClient,
)

__all__ = ["DailySummary", "OuraAPIError", "OuraClient"]
