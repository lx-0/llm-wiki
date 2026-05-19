"""Health Collector — daily biometric rollups from Oura API + Apple HealthKit XML.

Phase 1 (shipped 2026-05-15): Oura only. `.ytstack/AD-HOC-health-phase-1-PLAN.md`.
Phase 2 (M023, 2026-05-19): Apple HealthKit XML drop-folder.

Per-account schema under `CONFIG.personal.accounts.<id>.health`:

    health:
      oura:                          # Phase 1
        kind: oura-pat
        api_key_env: OURA_PRIVATE_PAT
        backfill_days: null
      healthkit:                     # Phase 2 (M023)
        kind: healthkit-xml-export
        inbox_dir: ~/.../inbox/health-export   # folder holding Export.xml
        filename: Export.xml                   # optional, default Export.xml

Single md file per (account, day) at `raw/notes/health/<YYYY>/<date>--<slug>.md`.
Oura wins for overlap keys (sleep / hrv / readiness / scores / resting_hr from
the API). HealthKit fills weight, steps, distance, energy, workouts, and the
long-tail history before Oura's backfill window. Re-runs are idempotent on
both sides — Oura via skip-existing on filename; HealthKit via SHA256 of
Export.xml stored in state (unchanged hash → no-op for that account).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from adapters.health.healthkit_xml import (
    HealthKitDailyAggregate,
    iter_aggregates as iter_healthkit_aggregates,
)
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
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def _slug_account(account_id: str) -> str:
    s = _ACCOUNT_SLUG_RE.sub("-", account_id.lower()).strip("-")
    return s or "account"


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Streaming SHA256 — bounded memory regardless of file size."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _merge_healthkit_into_path(
    target: Path,
    agg: HealthKitDailyAggregate,
    *,
    account_id: str,
) -> bool:
    """Merge HealthKit aggregate into `target` (create or update).

    Returns True when the file's content changed (new file OR new keys
    merged in); False when content was byte-identical to existing.

    Merge rule: Oura keys already in frontmatter win — we never overwrite
    a key the existing file has (sleep_hours, sleep_score, hrv_overnight,
    readiness_score, resting_hr, steps from Oura). HealthKit-only keys
    (weight_kg, body_fat_pct, distance_km, ..., workouts) are added.
    `sources` is set-unioned to {oura, healthkit}.
    """
    hk_fm = agg.to_frontmatter()
    if not hk_fm:
        return False

    if target.exists():
        text = target.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if m:
            fm_text, body = m.group(1), m.group(2)
            try:
                existing: dict = yaml.safe_load(fm_text) or {}
                if not isinstance(existing, dict):
                    existing = {}
            except yaml.YAMLError:
                log.warning(
                    "healthkit: frontmatter in %s is not valid YAML — rebuilding from scratch",
                    target,
                )
                existing = {}
        else:
            # File without frontmatter — treat as new (body lost, but health
            # files only ever carry an Oura/HealthKit frontmatter + boilerplate body).
            existing, body = {}, text
    else:
        existing = {}
        body = ""

    changed = False
    base = dict(existing) if existing else {
        "title": f"Health — {agg.day}",
        "type": "health-rollup",
        "date": agg.day,
        "account": account_id,
        "sources": [],
        "sensitivity": "high",
    }
    # Ensure mandatory keys exist even when merging into an Oura file
    base.setdefault("title", f"Health — {agg.day}")
    base.setdefault("type", "health-rollup")
    base.setdefault("date", agg.day)
    base.setdefault("account", account_id)
    base.setdefault("sensitivity", "high")

    # Source-union
    sources = base.get("sources")
    if not isinstance(sources, list):
        sources = []
    if "healthkit" not in sources:
        sources.append("healthkit")
        changed = True
    base["sources"] = sources

    # HealthKit-only keys: don't overwrite Oura
    for k, v in hk_fm.items():
        if k in base:
            continue
        base[k] = v
        changed = True

    if not changed:
        return False

    # Reorder for stable, human-readable layout: identity → sources →
    # Oura keys (any) → HealthKit keys → sensitivity.
    ordered: dict = {}
    for k in ("title", "type", "date", "account", "sources"):
        if k in base:
            ordered[k] = base[k]
    oura_keys = ("sleep_hours", "sleep_score", "readiness_score",
                 "hrv_overnight", "steps", "resting_hr")
    for k in oura_keys:
        if k in base and k not in ordered:
            ordered[k] = base[k]
    hk_keys = ("weight_kg", "body_fat_pct", "lean_body_mass_kg", "bmi",
               "height_cm", "steps_total", "distance_km",
               "active_energy_kcal", "basal_energy_kcal",
               "flights_climbed", "workouts")
    for k in hk_keys:
        if k in base and k not in ordered:
            ordered[k] = base[k]
    # Anything else (forward-compat) flushes through here unchanged
    for k, v in base.items():
        if k not in ordered and k != "sensitivity":
            ordered[k] = v
    if "sensitivity" in base:
        ordered["sensitivity"] = base["sensitivity"]

    yaml_block = yaml.dump(ordered, sort_keys=False, allow_unicode=True).strip()
    if not body.strip():
        body = f"\n# Health — {agg.day}\n\n(Add observations below as needed.)\n"
    elif not body.startswith("\n"):
        body = "\n" + body
    new_text = f"---\n{yaml_block}\n---\n{body}"

    # Re-check byte-equality after rebuild: re-ordering an existing file can
    # produce identical bytes when no HK keys were genuinely new.
    if target.exists() and target.read_text(encoding="utf-8") == new_text:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    return True


# ── Resolved per-account config ──────────────────────────────────────


@dataclass(frozen=True)
class _HealthAccount:
    """Resolved health-config for one `personal.accounts.<id>` entry (Phase 1: oura-pat)."""
    account_id: str
    oura_api_key: str         # resolved from os.environ at resolution time
    backfill_days: int


@dataclass(frozen=True)
class _HealthKitAccount:
    """Resolved healthkit-config for one `personal.accounts.<id>` entry.

    Phase 2 (M023). `inbox_dir` resolved with `~` expansion; an empty value
    means the account opted out (collector silently skips it).
    """
    account_id: str
    inbox_dir: Path
    filename: str  # default "Export.xml"


def _resolve_healthkit_accounts() -> list[_HealthKitAccount]:
    """Iterate CONFIG.personal.accounts for entries with health.healthkit.kind == 'healthkit-xml-export'.

    Accounts whose `inbox_dir` is empty or whose target file doesn't exist
    are still returned — the per-account runner reports the missing file
    in its message (mirrors Oura's missing-env-key surfacing).
    """
    out: list[_HealthKitAccount] = []
    accounts = CONFIG.personal.accounts or {}
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        health_block = body.get("health")
        if not isinstance(health_block, dict):
            continue
        hk_block = health_block.get("healthkit")
        if not isinstance(hk_block, dict) or hk_block.get("kind") != "healthkit-xml-export":
            continue
        raw_dir = (hk_block.get("inbox_dir") or "").strip()
        inbox = Path(raw_dir).expanduser() if raw_dir else Path("")
        filename = (hk_block.get("filename") or "Export.xml").strip() or "Export.xml"
        out.append(_HealthKitAccount(
            account_id=aid,
            inbox_dir=inbox,
            filename=filename,
        ))
    return out


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
        self._healthkit_accounts = _resolve_healthkit_accounts()
        self._timeout_s = float(CONFIG.limits.oura_request_timeout_s)

    def is_configured(self) -> bool:
        """True when at least one account has a usable Oura key OR a HealthKit export.

        Accounts whose env-var resolves empty don't count — piggyback should
        silently skip until the operator exports at least one PAT or drops
        a HealthKit export into a configured inbox.
        """
        if self._accounts and any(a.oura_api_key for a in self._accounts):
            return True
        for hk in self._healthkit_accounts:
            export = hk.inbox_dir / hk.filename
            if hk.inbox_dir and export.exists():
                return True
        return False

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self._accounts and not self._healthkit_accounts:
            log.info("HealthCollector: no accounts configured (Oura or HealthKit) — skipping.")
            return RunResult(message="no-op (no health accounts configured)")

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
            per_acct_messages.append(f"{acct.account_id} oura: {msg}")
            any_state_touched = any_state_touched or state_touched

        for hk in self._healthkit_accounts:
            try:
                msg, files, skipped, state_touched = self._run_one_healthkit_account(
                    hk,
                    state=state,
                    dry_run=dry_run,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("HealthCollector[%s] healthkit: unexpected", hk.account_id)
                per_acct_messages.append(f"{hk.account_id} healthkit: ERROR {type(e).__name__}: {e}")
                continue
            all_files.extend(files)
            total_skipped += skipped
            per_acct_messages.append(f"{hk.account_id} healthkit: {msg}")
            any_state_touched = any_state_touched or state_touched

        if not dry_run and any_state_touched:
            save_json_state(_STATE_FILE, state)

        touched_ids = tuple({a.account_id for a in self._accounts} |
                            {h.account_id for h in self._healthkit_accounts})
        return RunResult(
            files_written=tuple(all_files),
            files_skipped=total_skipped,
            state_keys_touched=touched_ids if any_state_touched else (),
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

    # ── HealthKit (Phase 2, M023) ────────────────────────────────────

    def _run_one_healthkit_account(
        self,
        acct: _HealthKitAccount,
        *,
        state: dict,
        dry_run: bool,
    ) -> tuple[str, list[Path], int, bool]:
        """Stream Export.xml, merge per-day aggregates into the substrate files.

        Idempotent: SHA256 of Export.xml stored in state. Unchanged hash →
        no-op (skip the parse entirely). Changed/new → full re-pass; per-day
        merge is itself idempotent on its own output, so the cost of a
        re-pass after a fresh export is bounded by per-day file rewrites.
        """
        if not acct.inbox_dir:
            return "no-op (inbox_dir unset)", [], 0, False
        export_path = acct.inbox_dir / acct.filename
        if not export_path.exists():
            return f"no-op (no {acct.filename} at {acct.inbox_dir})", [], 0, False

        per_acct = state.get(acct.account_id) or {}
        hk_state = per_acct.get("healthkit") or {}
        prior_hash = hk_state.get("last_export_hash")

        log.info(
            "HealthCollector[%s] healthkit: hashing %s (%d bytes)",
            acct.account_id, export_path, export_path.stat().st_size,
        )
        new_hash = _sha256_file(export_path)
        if prior_hash == new_hash:
            return f"no-op (export unchanged, sha256={new_hash[:12]}…)", [], 0, False

        log.info(
            "HealthCollector[%s] healthkit: streaming aggregates (hash %s%s)",
            acct.account_id,
            new_hash[:12],
            f", was {prior_hash[:12]}…" if prior_hash else " — first ingest",
        )

        files_written: list[Path] = []
        skipped_unchanged = 0
        account_slug = _slug_account(acct.account_id)
        days_seen = 0
        days_with_data = 0

        for agg in iter_healthkit_aggregates(export_path):
            days_seen += 1
            if agg.is_empty():
                continue
            days_with_data += 1
            year = agg.day.split("-", 1)[0] if "-" in agg.day else "unknown"
            output_dir = ROOT_DIR / self.SPEC.output_subfolder / year
            fname = f"{agg.day}--{account_slug}.md"
            target = output_dir / fname

            if dry_run:
                log.info("  DRY[%s] healthkit: would touch %s",
                         acct.account_id, target.relative_to(ROOT_DIR))
                continue

            changed = _merge_healthkit_into_path(
                target, agg, account_id=acct.account_id
            )
            if changed:
                files_written.append(target)
                # Only enrich the per-day rollup when Oura already wrote one
                # for this day. Bulk HealthKit ingest with 10+ years of
                # history would otherwise create thousands of empty
                # `daily/<YYYY-MM-DD>/` folders for dates the operator has
                # no other activity for. The Oura collector owns the
                # rollup's existence; HealthKit only adds keys on overlap.
                daily_health_file = (
                    ROOT_DIR / "daily" / agg.day / "health.md"
                )
                if daily_health_file.exists():
                    self._update_daily_rollup_healthkit(agg, acct.account_id)
            else:
                skipped_unchanged += 1

        state_touched = False
        if not dry_run:
            hk_state["last_export_hash"] = new_hash
            hk_state["last_ingested_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            hk_state["last_days_with_data"] = days_with_data
            per_acct["healthkit"] = hk_state
            state[acct.account_id] = per_acct
            state_touched = True

        return (
            f"parsed {days_seen} days · wrote {len(files_written)} · "
            f"unchanged {skipped_unchanged}",
            files_written,
            skipped_unchanged,
            state_touched,
        )

    @staticmethod
    def _update_daily_rollup_healthkit(agg: HealthKitDailyAggregate, account_id: str) -> None:
        """One-liner per (account, day) into `daily/<day>/health.md`.

        Same side-effect contract as the Oura rollup — `daily_capture.append`
        appends a line; multiple sources accumulate per day. We only emit
        keys that aren't redundant with Oura's typical line (steps + weight +
        workouts; sleep/HRV/scores stay on the Oura line).
        """
        bits: list[str] = []
        if agg.weight_kg is not None:
            bits.append(f"weight {agg.weight_kg:.1f}kg")
        if agg.body_fat_pct is not None:
            bits.append(f"bf {agg.body_fat_pct:.1f}%")
        if agg.steps_total is not None:
            bits.append(f"{agg.steps_total} steps (HK)")
        if agg.distance_km is not None:
            bits.append(f"{agg.distance_km:.1f}km")
        if agg.workouts:
            bits.append(f"{len(agg.workouts)} workout{'s' if len(agg.workouts) != 1 else ''}")
        if not bits:
            return
        line = f"- **{account_id}** (HK) · {' · '.join(bits)}"
        try:
            daily_capture.append(agg.day, "health", line)
        except Exception:  # noqa: BLE001
            log.exception("daily-rollup append failed for %s/%s (healthkit)", agg.day, account_id)

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
