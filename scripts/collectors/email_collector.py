"""Email Collector — substrate-level orchestration over MailboxReader adapters.

Iterates `CONFIG.personal.accounts`, resolves a MailboxReader per account
(via `adapters.mailbox.resolve_reader`), and runs one of two scan modes:

- **Full sweep** (`incremental=False`, e.g. `wiki collect email`): a
  complete metadata sweep, one overview report per account at
  `raw/notes/email/<account>-<date>.md`.
- **Incremental** (`incremental=True`, the daily piggyback): scans only
  messages newer than the per-account watermark in `state/email-state.json`,
  writes a delta report at `raw/notes/email/<account>-delta-<ts>.md`. The
  first incremental run for an account records a baseline watermark and
  scans nothing — the operator's one-time bulk ingest is not re-emitted.

Both modes advance the per-account `last_run_ts` watermark. State shape:
`{"accounts": {<account_id>: {"last_run_ts": "<iso>"}}}`. The legacy
pre-M002 per-mbox shape is migrated on read (see `_load_state`).

Accounts whose `reader.kind` doesn't resolve to an adapter (or whose
`reader` block is missing) are skipped silently. Empty config → no work,
no error (graceful agnostic).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from adapters.mailbox import MailboxReader, MailboxReadError, resolve_reader
from collectors.base import Collector, CollectorSpec, RunResult, register
from core.paths import EMAIL_STATE_FILE, ROOT_DIR
from core.utils import now_iso, today_iso
from domain.mail import MessageMeta
from core.config import CONFIG

log = logging.getLogger(__name__)


@register
class EmailCollector:
    SPEC = CollectorSpec(
        name="email",
        output_subfolder="raw/notes/email",
        piggyback_default=True,
        piggyback_cooldown_hours=24,
        supports_incremental=True,
        supports_account_loop=True,
    )

    def __init__(self) -> None:
        # Resolve readers eagerly so is_configured() reflects reality.
        # account_id → (account_dict, reader_or_None) — we keep the dict
        # for downstream use even when reader is None (debug logs etc.)
        self._accounts: list[tuple[str, dict, MailboxReader | None]] = []
        for account_id, account in (CONFIG.personal.accounts or {}).items():
            reader = resolve_reader(account)
            self._accounts.append((account_id, account, reader))

    def is_configured(self) -> bool:
        """True iff at least one account resolves to a non-None Reader.

        Zero accounts, or all-None readers (S01 stub state), or empty
        Personal config → False, collector is skipped by piggyback discovery.
        """
        return any(reader is not None for _, _, reader in self._accounts)

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        output_root = ROOT_DIR / self.SPEC.output_subfolder
        active_accounts = [
            (aid, acc, reader) for aid, acc, reader in self._accounts if reader is not None
        ]
        if not active_accounts:
            log.info("EmailCollector: no accounts configured — skipping.")
            return RunResult(message="no-op (no accounts with resolvable reader)")

        if incremental:
            return self._run_incremental(active_accounts, output_root, dry_run=dry_run)
        return self._run_full(active_accounts, output_root, dry_run=dry_run)

    # ── Full sweep ───────────────────────────────────────────────────
    def _run_full(
        self,
        active_accounts: list[tuple[str, dict, MailboxReader]],
        output_root: Path,
        *,
        dry_run: bool,
    ) -> RunResult:
        """Complete metadata sweep — one overview report per account.

        Advances each account's watermark so a subsequent incremental run
        picks up only what arrived after this sweep. A `MailboxReadError`
        (couldn't reach the mailbox) leaves that account's watermark and
        prior state untouched and is surfaced — never silently swallowed.
        """
        files_written: list[Path] = []
        skipped = 0
        errors: list[str] = []
        run_start = now_iso()
        state = _load_state()
        accounts_state = state.setdefault("accounts", {})

        for account_id, _account, reader in active_accounts:
            log.info("EmailCollector: scanning %s", account_id)
            try:
                messages = list(reader.scan_metadata())
            except MailboxReadError as e:
                log.error("EmailCollector: %s — scan FAILED, watermark untouched: %s",
                          account_id, e)
                errors.append(f"{account_id}: {e}")
                if not dry_run:
                    _record_failure(accounts_state, account_id, str(e), run_start)
                continue

            if not messages:
                log.info("  %s: 0 messages — skipping report", account_id)
                skipped += 1
                if not dry_run:
                    _record_success(accounts_state, account_id, run_start)
                continue

            report_path = output_root / f"{account_id}-{today_iso()}.md"
            report_text = _render_report(account_id, messages)

            if dry_run:
                log.info("  DRY RUN: would write %d-msg report to %s", len(messages), report_path)
                continue

            output_root.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_text, encoding="utf-8")
            log.info("  wrote %d-msg report → %s", len(messages), report_path.relative_to(ROOT_DIR))
            files_written.append(report_path)
            _record_success(accounts_state, account_id, run_start)

        if not dry_run:
            _save_state(state)

        message = f"scanned {len(active_accounts)} account(s), wrote {len(files_written)} report(s)"
        if errors:
            message += f", {len(errors)} FAILED"
        return RunResult(
            files_written=tuple(files_written),
            files_skipped=skipped,
            state_keys_touched=("accounts",) if not dry_run else (),
            message=message,
            errors=tuple(errors),
        )

    # ── Incremental delta ────────────────────────────────────────────
    def _run_incremental(
        self,
        active_accounts: list[tuple[str, dict, MailboxReader]],
        output_root: Path,
        *,
        dry_run: bool,
    ) -> RunResult:
        """Scan only messages newer than each account's watermark.

        First run for an account (no watermark, or an unparseable one):
        record a baseline and emit nothing — the operator's one-time bulk
        ingest must not be re-dumped as a "delta". A successful run advances
        the watermark to the run start time (not the max message date — a
        bogus future-dated message must not push the watermark forward).

        A `MailboxReadError` (login/connect failure, missing credentials, …)
        leaves the watermark exactly where it was — so the next run retries
        the same window instead of skipping past unread mail — and records
        the error on the account's state entry. The failure is never
        silently swallowed.
        """
        files_written: list[Path] = []
        skipped = 0
        baselined: list[str] = []
        errors: list[str] = []
        run_start = now_iso()
        state = _load_state()
        accounts_state = state.setdefault("accounts", {})

        for account_id, _account, reader in active_accounts:
            prev = accounts_state.get(account_id) or {}
            since = _parse_since(prev.get("last_run_ts"))

            if since is None:
                if prev.get("last_run_ts"):
                    log.warning(
                        "EmailCollector: %s — unparseable watermark %r, re-baselining",
                        account_id, prev.get("last_run_ts"),
                    )
                else:
                    log.info("EmailCollector: %s — baseline recorded, no delta on first run",
                             account_id)
                baselined.append(account_id)
                if not dry_run:
                    _record_success(accounts_state, account_id, run_start)
                continue

            log.info("EmailCollector: %s — incremental scan since %s",
                     account_id, since.isoformat())
            try:
                messages = list(reader.scan_metadata(since=since))
            except MailboxReadError as e:
                # Scan failed — hold the watermark so the next run retries
                # this exact window, and surface the error instead of hiding it.
                log.error("EmailCollector: %s — scan FAILED, watermark held at %s: %s",
                          account_id, prev.get("last_run_ts"), e)
                errors.append(f"{account_id}: {e}")
                if not dry_run:
                    _record_failure(accounts_state, account_id, str(e), run_start)
                continue

            if messages:
                report_path = output_root / f"{account_id}-delta-{_now_slug()}.md"
                report_text = _render_delta_report(account_id, messages, since=since)
                if dry_run:
                    log.info("  DRY RUN: would write %d-msg delta to %s",
                             len(messages), report_path)
                else:
                    output_root.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(report_text, encoding="utf-8")
                    log.info("  wrote %d-msg delta → %s",
                             len(messages), report_path.relative_to(ROOT_DIR))
                    files_written.append(report_path)
            else:
                log.info("  %s: 0 new messages since watermark", account_id)
                skipped += 1

            if not dry_run:
                _record_success(accounts_state, account_id, run_start)

        if not dry_run:
            _save_state(state)

        message = (
            f"incremental: {len(active_accounts)} account(s), "
            f"{len(files_written)} delta report(s), "
            f"{len(baselined)} baselined, {skipped} with no new mail"
        )
        if errors:
            message += f", {len(errors)} FAILED"
        return RunResult(
            files_written=tuple(files_written),
            files_skipped=skipped,
            state_keys_touched=("accounts",) if not dry_run else (),
            message=message,
            errors=tuple(errors),
        )


# ── Report rendering ─────────────────────────────────────────────────
# Stable shape — preserves what scripts/scan-email.py used to emit.
# When S03 lands Gmail, shape stays identical (only the source backend changes).

def _render_report(account_id: str, messages: list[MessageMeta]) -> str:
    if not messages:
        return ""
    folders = Counter(m.folder for m in messages)
    senders = Counter(m.from_addr for m in messages)
    earliest = min(m.date for m in messages)
    latest = max(m.date for m in messages)

    lines = [
        "---",
        "type: note",
        f"date: {today_iso()}",
        f'origin: "scan-email/{account_id}"',
        "tags: [email, metadata, overview]",
        "---",
        "",
        f"# Email overview — {account_id}",
        "",
        f"> {len(messages):,} messages from {len(senders):,} senders across "
        f"{len(folders):,} folders, "
        f"{earliest:%Y-%m-%d}–{latest:%Y-%m-%d}.",
        "",
        "## Folders",
        "",
        "| Folder | Messages |",
        "|---|---:|",
    ]
    for folder, n in folders.most_common():
        lines.append(f"| `{folder}` | {n} |")

    lines.extend(["", "## Top senders (top 20)", "", "| Sender | Messages |", "|---|---:|"])
    for sender, n in senders.most_common(20):
        lines.append(f"| `{sender}` | {n} |")

    lines.append("")
    return "\n".join(lines)


def _render_delta_report(
    account_id: str, messages: list[MessageMeta], *, since: datetime
) -> str:
    """Delta sibling of `_render_report` — only messages newer than the watermark.

    One file per account. Unlike the full-sweep overview (which aggregates,
    because a mailbox can hold 50k messages), a delta is a bounded set — so
    it lists each new message: date+time, sender, subject. The subject is the
    highest-signal field and is what the compiler actually distils from; the
    timestamp orders same-day messages and lets the compiler reason about
    recency. Grouped by folder, newest message first.
    """
    folders = Counter(m.folder for m in messages)

    lines = [
        "---",
        "type: email-delta",
        f"date: {today_iso()}",
        f'origin: "scan-email/{account_id}/delta"',
        "tags: [email, metadata, delta]",
        "language: de",
        "---",
        "",
        f"# Email Delta — {account_id}",
        "",
        f"> Inkrementeller Scan vom {today_iso()}. "
        f"{len(messages):,} neue Mails seit {since:%Y-%m-%d %H:%M} "
        f"in {len(folders):,} Ordner(n).",
        "",
    ]

    for folder, _n in folders.most_common():
        folder_msgs = sorted(
            (m for m in messages if m.folder == folder),
            key=lambda m: m.date,
            reverse=True,
        )
        f_earliest = min(m.date for m in folder_msgs)
        f_latest = max(m.date for m in folder_msgs)
        lines.append(
            f"## {folder}  ({len(folder_msgs):,} neue Mails · "
            f"{f_earliest:%Y-%m-%d}–{f_latest:%Y-%m-%d})"
        )
        for m in folder_msgs:
            subject = " ".join(m.subject.split()) or "(kein Betreff)"
            sender = m.from_addr or "(unbekannt)"
            lines.append(f"- `{m.date:%m-%d %H:%M}` {sender} — {subject}")
        lines.append("")

    return "\n".join(lines)


# ── State persistence ────────────────────────────────────────────────
# Per-account incremental watermarks. Shape:
#   {"accounts": {<account_id>: {"last_run_ts": "<iso8601>",
#                                "last_error": "<msg>",          # only if last scan failed
#                                "last_error_at": "<iso8601>"}}}

def _record_success(accounts_state: dict, account_id: str, run_start: str) -> None:
    """Advance the watermark and drop any prior error — the scan completed.

    Replacing the whole entry (rather than mutating `last_run_ts`) is what
    clears a stale `last_error` / `last_error_at`, so the state file always
    reflects current health.
    """
    accounts_state[account_id] = {"last_run_ts": run_start}


def _record_failure(accounts_state: dict, account_id: str, error: str, at: str) -> None:
    """Record a scan failure WITHOUT touching the watermark.

    The watermark stays exactly where it was so the next run retries the
    same window — no silent skip past unread mail. `last_error` /
    `last_error_at` make the failure visible and let a recovered account be
    detected (the next `_record_success` clears them).
    """
    entry = dict(accounts_state.get(account_id) or {})
    entry["last_error"] = error
    entry["last_error_at"] = at
    accounts_state[account_id] = entry


def _now_slug() -> str:
    """Filename timestamp slug in local time: 2026-05-14T1830."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H%M")


def _parse_since(raw: str | None) -> datetime | None:
    """Parse a stored watermark into a tz-aware datetime.

    Returns None for a missing or unparseable value — the caller treats
    that as "no watermark" and re-baselines instead of crashing or doing
    a full dump. Naive timestamps are assumed UTC (the Thunderbird reader
    normalises message dates to UTC-aware, so `since` must be aware too).
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _load_state() -> dict:
    """Load `email-state.json`, migrating the legacy pre-M002 shape on read.

    Legacy shape (`scripts/scan-email.py`): per-mbox-file size trackers
    `{"mboxes": {<rel_path>: {...}}, "last_incremental": "<date>"}`. The
    new EmailCollector keys watermarks per account, so the per-mbox entries
    can't be reused — but `last_incremental` is salvaged: it seeds the
    initial `last_run_ts` for every configured account, so the first
    incremental run after the upgrade picks up the gap since that date
    instead of silently re-baselining.
    """
    if not EMAIL_STATE_FILE.exists():
        return {"accounts": {}}
    try:
        data = json.loads(EMAIL_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accounts": {}}
    if not isinstance(data, dict):
        return {"accounts": {}}
    if isinstance(data.get("accounts"), dict):
        return data
    # Legacy per-mbox shape — migrate.
    if "mboxes" in data:
        accounts: dict[str, dict] = {}
        legacy_date = data.get("last_incremental")
        if legacy_date:
            watermark = f"{legacy_date}T00:00:00+00:00"
            for account_id in (CONFIG.personal.accounts or {}):
                accounts[account_id] = {"last_run_ts": watermark}
            log.info(
                "EmailCollector: migrated legacy email-state.json — seeded "
                "%d account(s) with watermark %s", len(accounts), watermark,
            )
        return {"accounts": accounts}
    return {"accounts": {}}


def _save_state(state: dict) -> None:
    EMAIL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
