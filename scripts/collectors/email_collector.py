"""Email Collector — substrate-level orchestration over MailboxReader adapters.

Iterates `CONFIG.personal.accounts`, resolves a MailboxReader per account
(via `adapters.mailbox.resolve_reader`), runs a metadata sweep, writes one
markdown report per account into `raw/notes/email/<account>-<date>.md`.

Accounts whose `reader.kind` doesn't resolve to an adapter (or whose
`reader` block is missing) are skipped silently. Empty config → no work,
no error (graceful agnostic).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from adapters.mailbox import MailboxReader, resolve_reader
from collectors.base import Collector, CollectorSpec, RunResult, register
from config import RAW_DIR, ROOT_DIR, today_iso
from domain.mail import MessageMeta
from wiki_config import CONFIG

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
        files_written: list[Path] = []
        skipped = 0

        active_accounts = [
            (aid, acc, reader) for aid, acc, reader in self._accounts if reader is not None
        ]
        if not active_accounts:
            log.info("EmailCollector: no accounts configured — skipping.")
            return RunResult(message="no-op (no accounts with resolvable reader)")

        for account_id, _account, reader in active_accounts:
            log.info("EmailCollector: scanning %s", account_id)
            messages = list(reader.scan_metadata())
            if not messages:
                log.info("  %s: 0 messages — skipping report", account_id)
                skipped += 1
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

        return RunResult(
            files_written=tuple(files_written),
            files_skipped=skipped,
            message=f"scanned {len(active_accounts)} account(s), wrote {len(files_written)} report(s)",
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
