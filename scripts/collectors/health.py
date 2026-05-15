"""Health Collector — pulls daily biometric rollups from the Oura Ring API.

Phase 1 scope (`.ytstack/AD-HOC-health-phase-1-PLAN.md`):
- Oura only. HealthKit XML drop-folder is Phase 2.
- Multi-tenant from day one — per-account `health:` sub-block under
  `CONFIG.personal.accounts.<id>` with `kind: oura-pat`. Mirrors jamie/gmeet.
- Single Bearer-PAT auth, env-var-referenced (never the key itself in config).
- One md file per (account, day) in `raw/notes/health/<year>/`.
- Skip-existing keyed on filename match; idempotent re-runs.
- Watermark on success only: `state['<account>']['oura']['last_day'] = ISO date`.
  Failed account leaves its watermark untouched.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from adapters.health.oura import DailySummary, OuraAPIError, OuraClient
from collectors.base import CollectorSpec, RunResult, register
from core import daily_capture
from core.config import CONFIG
from core.paths import ROOT_DIR, STATE_DIR
from core.utils import load_json_state, save_json_state

log = logging.getLogger(__name__)

_STATE_FILE = STATE_DIR / "health-state.json"
_OUTPUT_SUBFOLDER = "raw/notes/health"
_DEFAULT_BACKFILL_DAYS = 90

_ACCOUNT_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug_account(account_id: str) -> str:
    s = _ACCOUNT_SLUG_RE.sub("-", account_id.lower()).strip("-")
    return s or "account"


# ── Resolved per-account config ──────────────────────────────────────


@dataclass(frozen=True)
class _HealthAccount:
    """Resolved health-config for one `personal.accounts.<id>` entry (Phase 1: oura-pat)."""
    account_id: str
    oura_api_key: str         # resolved from os.environ at resolution time
    backfill_days: int


def _resolve_health_accounts() -> list[_HealthAccount]:
    """Iterate CONFIG.personal.accounts for entries with health.oura.kind == 'oura-pat'.

    Accounts whose api_key_env resolves to an empty/unset env var are still
    returned — `_run_one_account` reports the missing key in its message
    (mirrors jamie/gmeet per-account error surfacing). Phase 1 ignores any
    `health.healthkit` sub-block (deferred).
    """
    out: list[_HealthAccount] = []
    accounts = CONFIG.personal.accounts or {}
    default_backfill = CONFIG.limits.oura_max_backfill_days
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        health_block = body.get("health")
        if not isinstance(health_block, dict):
            continue
        oura_block = health_block.get("oura")
        if not isinstance(oura_block, dict) or oura_block.get("kind") != "oura-pat":
            continue
        env_name = (oura_block.get("api_key_env") or "").strip()
        api_key = os.environ.get(env_name, "").strip() if env_name else ""
        per_acct_backfill = oura_block.get("backfill_days")
        out.append(_HealthAccount(
            account_id=aid,
            oura_api_key=api_key,
            backfill_days=int(per_acct_backfill) if per_acct_backfill is not None else default_backfill,
        ))
    return out


# ── Rendering ────────────────────────────────────────────────────────


def _render_markdown(summary: DailySummary, *, account_id: str) -> str:
    """One markdown file per (account, day). Frontmatter is the value, body minimal.

    All Oura-sourced fields go in frontmatter — query/lint can grep numerically
    without parsing prose. The body is a minimal heading + optional narrative
    slot for the operator to add observations.
    """
    # Build frontmatter as a python dict for yaml.dump — emits stable key order
    # and handles None → null. We explicitly drop None-valued keys so the
    # rendered frontmatter doesn't carry "sleep_hours: null" noise.
    frontmatter: dict = {
        "title": f"Health — {summary.day}",
        "type": "health-rollup",
        "date": summary.day,
        "account": account_id,
        "sources": ["oura"],
    }
    metric_fields = (
        ("sleep_hours", round(summary.sleep_hours, 2) if summary.sleep_hours is not None else None),
        ("sleep_score", summary.sleep_score),
        ("readiness_score", summary.readiness_score),
        ("hrv_overnight", summary.hrv_overnight),
        ("steps", summary.steps),
        ("resting_hr", summary.resting_hr),
    )
    for field_name, value in metric_fields:
        if value is not None:
            frontmatter[field_name] = value
    frontmatter["sensitivity"] = "high"

    yaml_block = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    body = f"# Health — {summary.day}\n\n(Add observations below as needed.)\n"
    return f"---\n{yaml_block}\n---\n\n{body}"


# ── Collector ────────────────────────────────────────────────────────


@register
class HealthCollector:
    SPEC = CollectorSpec(
        name="health",
        output_subfolder=_OUTPUT_SUBFOLDER,
        piggyback_default=True,
        piggyback_cooldown_hours=24,
        supports_incremental=True,
        supports_account_loop=True,
    )

    def __init__(self) -> None:
        self._accounts = _resolve_health_accounts()
        self._timeout_s = float(CONFIG.limits.oura_request_timeout_s)

    def is_configured(self) -> bool:
        """At least one account has health.oura.kind == 'oura-pat' AND a resolved key.

        Accounts whose env-var resolves empty don't count — piggyback should
        silently skip until the operator exports at least one PAT.
        """
        if not self._accounts:
            return False
        return any(a.oura_api_key for a in self._accounts)

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self._accounts:
            log.info("HealthCollector: no accounts with health.oura.kind=oura-pat — skipping.")
            return RunResult(message="no-op (no oura accounts configured)")

        all_files: list[Path] = []
        total_skipped = 0
        per_acct_messages: list[str] = []
        any_state_touched = False

        state = load_json_state(_STATE_FILE)

        for acct in self._accounts:
            try:
                msg, files, skipped, state_touched = self._run_one_account(
                    acct,
                    state=state,
                    dry_run=dry_run,
                    incremental=incremental,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("HealthCollector[%s]: unexpected", acct.account_id)
                per_acct_messages.append(f"{acct.account_id}: ERROR {type(e).__name__}: {e}")
                continue
            all_files.extend(files)
            total_skipped += skipped
            per_acct_messages.append(f"{acct.account_id}: {msg}")
            any_state_touched = any_state_touched or state_touched

        if not dry_run and any_state_touched:
            save_json_state(_STATE_FILE, state)

        return RunResult(
            files_written=tuple(all_files),
            files_skipped=total_skipped,
            state_keys_touched=tuple(a.account_id for a in self._accounts) if any_state_touched else (),
            message=" · ".join(per_acct_messages) or "no-op",
        )

    def _run_one_account(
        self,
        acct: _HealthAccount,
        *,
        state: dict,
        dry_run: bool,
        incremental: bool,
    ) -> tuple[str, list[Path], int, bool]:
        """Run one account's scan. Returns (message, files, skipped, state_touched).

        Mutates `state[acct.account_id]['oura']['last_day']` only on success
        that actually advanced the watermark. Failures leave the watermark
        untouched (matches jamie/gmeet failure-vs-empty discipline).
        """
        if not acct.oura_api_key:
            return "no-op (oura api_key_env unset)", [], 0, False

        per_acct = state.get(acct.account_id) or {}
        oura_state = per_acct.get("oura") or {}
        last_day = oura_state.get("last_day") if incremental else None

        end_date = date.today().isoformat()
        if last_day:
            try:
                start = (datetime.fromisoformat(last_day).date() + timedelta(days=1)).isoformat()
            except ValueError:
                log.warning("HealthCollector[%s]: invalid last_day %r — falling back to backfill",
                            acct.account_id, last_day)
                start = (date.today() - timedelta(days=acct.backfill_days)).isoformat()
        else:
            start = (date.today() - timedelta(days=acct.backfill_days)).isoformat()

        if start > end_date:
            return f"no-op (watermark {last_day} ≥ today {end_date})", [], 0, False

        log.info(
            "HealthCollector[%s]: fetching oura window %s → %s",
            acct.account_id, start, end_date,
        )

        client = OuraClient(api_key=acct.oura_api_key, timeout_s=self._timeout_s)
        try:
            summaries = client.fetch_daily_summaries(start_date=start, end_date=end_date)
        except OuraAPIError as e:
            log.error("HealthCollector[%s]: oura fetch failed: %s", acct.account_id, e)
            return f"oura fetch failed: {e}", [], 0, False

        if not summaries:
            return f"no-op (0 days with data in {start}..{end_date})", [], 0, False

        files_written: list[Path] = []
        skipped = 0
        highest_day: str | None = oura_state.get("last_day")
        account_slug = _slug_account(acct.account_id)

        for summary in summaries:
            year = summary.day.split("-", 1)[0] if "-" in summary.day else "unknown"
            output_dir = ROOT_DIR / self.SPEC.output_subfolder / year
            fname = f"{summary.day}--{account_slug}.md"
            target = output_dir / fname

            if target.exists():
                skipped += 1
                if highest_day is None or summary.day > highest_day:
                    highest_day = summary.day
                continue

            md = _render_markdown(summary, account_id=acct.account_id)

            if dry_run:
                log.info("  DRY[%s]: would write %s (%d bytes)",
                         acct.account_id, target.relative_to(ROOT_DIR), len(md))
                continue

            output_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            log.info("  [%s] wrote %s", acct.account_id, target.relative_to(ROOT_DIR))
            files_written.append(target)

            # Mirror the day's key metrics into daily/<date>/health.md — one
            # line per (account, day), idempotent replace per account.
            self._update_daily_rollup(summary, acct.account_id)

            if highest_day is None or summary.day > highest_day:
                highest_day = summary.day

        state_touched = False
        if not dry_run and highest_day and highest_day != oura_state.get("last_day"):
            oura_state["last_day"] = highest_day
            per_acct["oura"] = oura_state
            state[acct.account_id] = per_acct
            state_touched = True

        return (
            f"fetched {len(summaries)} days · wrote {len(files_written)} · skipped {skipped}",
            files_written,
            skipped,
            state_touched,
        )

    @staticmethod
    def _update_daily_rollup(summary: DailySummary, account_id: str) -> None:
        """Mirror this summary's metrics into daily/<day>/health.md.

        Per-(account,day) one-liner. Multiple accounts append; same-account
        re-runs replace via the daily_capture KNOWN_SOURCES contract.

        The `daily/<day>/` subfolder substrate is the post-2026-05-15
        rollup layer — see `.ytstack/AD-HOC-daily-as-rollup-PLAN.md`.
        """
        bits: list[str] = []
        if summary.sleep_hours is not None:
            bits.append(f"sleep {summary.sleep_hours:.1f}h")
        if summary.sleep_score is not None:
            bits.append(f"score {summary.sleep_score}")
        if summary.readiness_score is not None:
            bits.append(f"readiness {summary.readiness_score}")
        if summary.hrv_overnight is not None:
            bits.append(f"hrv {summary.hrv_overnight}")
        if summary.steps is not None:
            bits.append(f"{summary.steps} steps")
        if summary.resting_hr is not None:
            bits.append(f"resting {summary.resting_hr}")
        if not bits:
            return
        line = f"- **{account_id}** · {' · '.join(bits)}"
        try:
            daily_capture.append(summary.day, "health", line)
        except Exception:  # noqa: BLE001
            # Rollup is a side-effect; never let it break the primary write.
            log.exception("daily-rollup append failed for %s/%s", summary.day, account_id)
