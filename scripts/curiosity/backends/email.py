"""Email-deep-scan consumer for curiosity requests.

Reads a `raw/requests/request-*.json` with `type: "email-deep-scan"`,
resolves the account's MailboxReader via `adapters.mailbox.resolve_reader`,
calls `scan_deep(folder, limit)` to pull full message bodies, renders one
markdown report into `raw/notes/email/deep-{slug}-{date}.md`, and marks
the request as done.

The compiled deep-scan markdown becomes a normal raw/notes/ source — the
next compile pass distills it into knowledge/ articles, closing the loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from adapters.mailbox import resolve_reader
from core.paths import RAW_DIR, ROOT_DIR
from core.utils import now_iso, today_iso
from core.config import CONFIG

log = logging.getLogger("curiosity")

DEEP_SCAN_DIR = RAW_DIR / "notes" / "email"
# Per-run cap on bodies pulled. Deep-scan is expensive (full bodies + IMAP/API
# round-trips); compile-pass downstream pays again to distill. Stay conservative.
DEFAULT_BODY_LIMIT = 50


@dataclass(frozen=True)
class RunResult:
    success: bool
    output_path: Path | None = None
    messages_pulled: int = 0
    error: str | None = None


def process_request(request_path: Path, *, body_limit: int = DEFAULT_BODY_LIMIT, dry_run: bool = False) -> RunResult:
    """Process one email-deep-scan request file.

    On success: writes the deep-scan markdown, updates request frontmatter to
    `status: "done"` + `processed_at: <iso>`. On failure: leaves status as
    `pending` (or `error`) with a written `last_error` field so re-runs can retry.
    """
    if not request_path.exists():
        return RunResult(success=False, error=f"request file not found: {request_path}")

    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return RunResult(success=False, error=f"invalid JSON: {exc}")

    if request.get("type") != "email-deep-scan":
        return RunResult(success=False, error=f"unsupported type: {request.get('type')!r}")

    if request.get("status") == "done":
        log.info("  Already done, skipping: %s", request_path.name)
        return RunResult(success=True, output_path=None, messages_pulled=0)

    account_id = request.get("account") or CONFIG.personal.primary_account
    folder = request.get("folder", "").strip()
    topic = request.get("topic", "").strip()
    rationale = request.get("rationale", "").strip()
    slug_match = request_path.stem.removeprefix("request-")  # request-{slug}-{date}

    if not account_id or not folder or not topic:
        return RunResult(success=False, error=f"incomplete request (account/folder/topic missing)")

    account_cfg = (CONFIG.personal.accounts or {}).get(account_id)
    if account_cfg is None:
        return _mark_error(request, request_path, f"account {account_id!r} not in CONFIG.personal.accounts")

    reader = resolve_reader(account_cfg)
    if reader is None:
        return _mark_error(request, request_path, f"no reader adapter resolved for account {account_id!r}")

    log.info("  Deep-scan %s/%s topic=%r (cap=%d)", account_id, folder, topic, body_limit)

    if dry_run:
        return RunResult(success=True, output_path=None, messages_pulled=0)

    try:
        messages = list(reader.scan_deep(folder=folder, limit=body_limit))
    except Exception as exc:
        return _mark_error(request, request_path, f"scan_deep failed: {exc!r}")

    DEEP_SCAN_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DEEP_SCAN_DIR / f"deep-{slug_match}.md"

    output_path.write_text(_render(request, messages, account_id), encoding="utf-8")
    log.info("  Wrote %s (%d messages)", output_path.relative_to(ROOT_DIR), len(messages))

    request["status"] = "done"
    request["processed_at"] = now_iso()
    request["output"] = str(output_path.relative_to(ROOT_DIR))
    request["messages_pulled"] = len(messages)
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    return RunResult(success=True, output_path=output_path, messages_pulled=len(messages))


def _mark_error(request: dict, request_path: Path, error: str) -> RunResult:
    request["status"] = "error"
    request["last_error"] = error
    request["last_attempt_at"] = now_iso()
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    log.warning("  Failed: %s", error)
    return RunResult(success=False, error=error)


def _render(request: dict, messages: list, account_id: str) -> str:
    """Markdown report — frontmatter + per-message section with body."""
    topic = request.get("topic", "")
    folder = request.get("folder", "")
    rationale = request.get("rationale", "")
    source = request.get("source", "")
    created = request.get("created", "")

    lines: list[str] = []
    lines.append("---")
    lines.append(f"type: note")
    lines.append(f"kind: email-deep-scan")
    lines.append(f"topic: {json.dumps(topic, ensure_ascii=False)}")
    lines.append(f"folder: {json.dumps(folder, ensure_ascii=False)}")
    lines.append(f"account: {account_id}")
    lines.append(f"origin: \"curiosity/email-deep-scan\"")
    lines.append(f"request_source: \"{source}\"")
    lines.append(f"request_created: \"{created}\"")
    lines.append(f"processed_at: \"{now_iso()}\"")
    lines.append(f"messages: {len(messages)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Deep scan — {topic}")
    lines.append("")
    lines.append(f"**Folder:** `{folder}` · **Account:** `{account_id}` · **Pulled:** {len(messages)} message(s)")
    lines.append("")
    lines.append(f"**Why this scan:** {rationale}")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not messages:
        lines.append("_No messages matched._")
        return "\n".join(lines) + "\n"

    # Sort newest-first for compile relevance.
    messages_sorted = sorted(messages, key=lambda m: m.meta.date, reverse=True)

    for msg in messages_sorted:
        meta = msg.meta
        when = meta.date.strftime("%Y-%m-%d %H:%M") if isinstance(meta.date, datetime) else str(meta.date)
        to_field = ", ".join(meta.to_addrs) if meta.to_addrs else "—"

        lines.append(f"## {meta.subject or '(no subject)'}")
        lines.append("")
        lines.append(f"- **From:** {meta.from_addr}")
        lines.append(f"- **To:** {to_field}")
        lines.append(f"- **Date:** {when}")
        if meta.in_reply_to:
            lines.append(f"- **In-reply-to:** `{meta.in_reply_to}`")
        if msg.attachment_filenames:
            attach = ", ".join(f"`{a}`" for a in msg.attachment_filenames)
            lines.append(f"- **Attachments:** {attach}")
        lines.append("")
        body = (msg.body_text or "").strip()
        # Cap body at 8 KB / message — keep total file under ~400 KB even at limit=50.
        if len(body) > 8000:
            body = body[:8000] + "\n\n…[truncated]"
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")

    return "\n".join(lines) + "\n"


def list_pending(requests_dir: Path | None = None) -> list[Path]:
    """Return request files with status != done, oldest first."""
    requests_dir = requests_dir or (ROOT_DIR / "raw" / "requests")
    if not requests_dir.exists():
        return []
    pending = []
    for p in sorted(requests_dir.glob("request-*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if r.get("type") != "email-deep-scan":
            continue
        if r.get("status") == "done":
            continue
        pending.append(p)
    return pending
