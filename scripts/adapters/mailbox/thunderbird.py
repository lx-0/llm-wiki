"""Thunderbird adapters — local mbox files + msgFilterRules.dat.

Two adapters in one module because they share the same source-of-truth
(a Thunderbird profile directory) and the same path-resolution rules.

- `ThunderbirdMboxReader` — read-side: mbox file walker + per-message
  header / body parser. Ported from the legacy `scripts/scan-email.py`.

- `ThunderbirdMsgFilter` — write-side: msgFilterRules.dat parser +
  writer with timestamped backup. Ported from the legacy
  `scripts/thunderbird-rules.py`. Note: rules added via this filter
  apply to FUTURE messages only (mid-session changes require a TB
  restart — that's a Thunderbird constraint, not an adapter quirk).
"""

from __future__ import annotations

import email.header
import email.utils
import logging
import mailbox
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from adapters.mailbox.base import ApplyResult
from domain.mail import (
    FilterAction,
    FilterCondition,
    FilterRule,
    Message,
    MessageMeta,
)

log = logging.getLogger(__name__)


# ── Reader ───────────────────────────────────────────────────────────


class ThunderbirdMboxReader:
    """Walks Thunderbird mbox files under `mbox_paths`."""

    def __init__(self, account_id: str, mbox_paths: list[Path]) -> None:
        self._account_id = account_id
        self._roots = [Path(p).expanduser() for p in mbox_paths]

    def list_folders(self) -> list[str]:
        names: set[str] = set()
        for root in self._roots:
            if not root.exists():
                continue
            for folder_name, _ in _find_mbox_files(root):
                names.add(folder_name)
        return sorted(names)

    def scan_metadata(
        self,
        folder: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[MessageMeta]:
        for root in self._roots:
            if not root.exists():
                continue
            for folder_name, mbox_path in _find_mbox_files(root, folder_filter=folder):
                yield from _iter_metadata(self._account_id, folder_name, mbox_path, since=since)

    def scan_deep(
        self,
        folder: str,
        limit: int = 0,
        since: datetime | None = None,
    ) -> Iterator[Message]:
        emitted = 0
        for root in self._roots:
            if not root.exists():
                continue
            for folder_name, mbox_path in _find_mbox_files(root, folder_filter=folder):
                if folder_name != folder:
                    continue
                for msg in _iter_deep(self._account_id, folder_name, mbox_path, since=since):
                    yield msg
                    emitted += 1
                    if limit and emitted >= limit:
                        return


def _find_mbox_files(
    base_path: Path,
    folder_filter: str | None = None,
) -> list[tuple[str, Path]]:
    """Recursively find mbox files. Returns (folder_name, path) sorted by folder_name."""
    results: list[tuple[str, Path]] = []
    if not base_path.exists():
        return results
    for path in base_path.rglob("*"):
        if path.is_dir() or path.suffix in (".msf", ".dat"):
            continue
        if path.name.startswith("."):
            continue
        rel = path.relative_to(base_path)
        # Skip Thunderbird's *.sbd shadow dirs in the folder name.
        folder_name = re.sub(r"\.sbd[/\\]", "/", str(rel))
        if folder_filter and folder_filter not in folder_name:
            continue
        results.append((folder_name, path))
    return sorted(results, key=lambda x: x[0])


def _decode_header(raw: str) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(raw)))
    except Exception:
        return raw


def _parse_date(raw: str) -> datetime | None:
    """Parse a Date: header into tz-aware UTC datetime.

    Some mbox messages have tz-aware dates, some don't (older Outlook/
    legacy clients). `min()` over a mixed set raises TypeError. Normalise
    to tz-aware UTC at parse time so downstream code never has to care.
    """
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except Exception:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iter_metadata(
    account_id: str,
    folder: str,
    path: Path,
    *,
    since: datetime | None,
) -> Iterator[MessageMeta]:
    try:
        mbox = mailbox.mbox(str(path))
    except Exception as e:  # noqa: BLE001
        log.warning("ThunderbirdMboxReader: cannot open %s: %s", path, e)
        return

    for key in mbox.keys():
        try:
            msg = mbox[key]
        except Exception:
            continue

        date = _parse_date(msg.get("Date", ""))
        if since is not None and date is not None and date < since:
            continue

        from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
        to_addrs = tuple(
            email.utils.parseaddr(part)[1]
            for part in (msg.get("To", "") or "").split(",")
            if part.strip()
        )

        yield MessageMeta(
            id=str(key),
            account_id=account_id,
            folder=folder,
            from_addr=from_addr or from_name,
            to_addrs=to_addrs,
            subject=_decode_header(msg.get("Subject", "")),
            date=date or datetime.fromtimestamp(0, timezone.utc),
            size_bytes=len(bytes(msg)) if hasattr(msg, "as_bytes") else 0,
            in_reply_to=msg.get("In-Reply-To"),
            message_id=msg.get("Message-ID"),
        )


def _iter_deep(
    account_id: str,
    folder: str,
    path: Path,
    *,
    since: datetime | None,
) -> Iterator[Message]:
    try:
        mbox = mailbox.mbox(str(path))
    except Exception as e:  # noqa: BLE001
        log.warning("ThunderbirdMboxReader: cannot open %s: %s", path, e)
        return

    for key in mbox.keys():
        try:
            msg = mbox[key]
        except Exception:
            continue

        date = _parse_date(msg.get("Date", ""))
        if since is not None and date is not None and date < since:
            continue

        from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
        to_addrs = tuple(
            email.utils.parseaddr(part)[1]
            for part in (msg.get("To", "") or "").split(",")
            if part.strip()
        )

        meta = MessageMeta(
            id=str(key),
            account_id=account_id,
            folder=folder,
            from_addr=from_addr or from_name,
            to_addrs=to_addrs,
            subject=_decode_header(msg.get("Subject", "")),
            date=date or datetime.fromtimestamp(0, timezone.utc),
            size_bytes=len(bytes(msg)) if hasattr(msg, "as_bytes") else 0,
            in_reply_to=msg.get("In-Reply-To"),
            message_id=msg.get("Message-ID"),
        )
        body_text = _extract_body(msg)
        attachments = tuple(_attachment_filenames(msg))
        yield Message(meta=meta, body_text=body_text, attachment_filenames=attachments)


def _extract_body(msg: mailbox.mboxMessage) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    return ""
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _attachment_filenames(msg: mailbox.mboxMessage) -> Iterator[str]:
    if not msg.is_multipart():
        return
    for part in msg.walk():
        disp = part.get("Content-Disposition", "")
        if "attachment" in disp.lower():
            name = part.get_filename()
            if name:
                yield _decode_header(name)


# ── Filter ───────────────────────────────────────────────────────────


@dataclass
class _DatRule:
    """Internal — one rule entry inside a msgFilterRules.dat file.

    Represents Thunderbird's on-disk shape. The Adapter translates between
    domain.mail.FilterRule (the canonical type) and this _DatRule.
    """

    name: str = ""
    enabled: str = "yes"
    rule_type: str = "17"
    actions: list[tuple[str, str | None]] = field(default_factory=list)
    condition: str = ""

    def to_dat(self) -> str:
        lines = [
            f'name="{self.name}"',
            f'enabled="{self.enabled}"',
            f'type="{self.rule_type}"',
        ]
        for action, value in self.actions:
            lines.append(f'action="{action}"')
            if value is not None:
                lines.append(f'actionValue="{value}"')
        lines.append(f'condition="{self.condition}"')
        return "\n".join(lines)


class ThunderbirdMsgFilter:
    """Writes rules into a Thunderbird msgFilterRules.dat file.

    Rules apply to FUTURE messages only — Thunderbird must restart to
    pick up changes. This is a TB constraint, surfaced via ApplyResult.message.
    """

    def __init__(self, account_id: str, filter_paths: list[Path]) -> None:
        self._account_id = account_id
        self._paths = [Path(p).expanduser() for p in filter_paths]

    def apply(self, rule: FilterRule, *, dry_run: bool = False) -> ApplyResult:
        target = next((p for p in self._paths if p.exists()), self._paths[0] if self._paths else None)
        if target is None:
            return ApplyResult(
                success=False,
                message=f"thunderbird-msgfilter: no filter_paths configured for {self._account_id}",
                dry_run=dry_run,
            )

        if dry_run:
            return ApplyResult(
                success=True,
                message=f"thunderbird-msgfilter: would write rule {rule.name!r} to {target}",
                dry_run=True,
            )

        version, logging_val, existing = _parse_filter_file(target)
        # Dedup by rule name — overwriting same-named rule is fine.
        existing = [r for r in existing if r.name != rule.name]
        existing.append(_to_dat_rule(rule))
        _backup(target)
        _write_filter_file(target, version, logging_val, existing)
        return ApplyResult(
            success=True,
            rule_id=rule.name,
            message=(
                f"thunderbird-msgfilter: wrote {rule.name!r} to {target} "
                f"({len(existing)} rules total). Restart Thunderbird to activate."
            ),
        )

    def list_existing(self) -> list[FilterRule]:
        out: list[FilterRule] = []
        for path in self._paths:
            if not path.exists():
                continue
            _version, _logging, dat_rules = _parse_filter_file(path)
            for dr in dat_rules:
                fr = _from_dat_rule(dr)
                if fr is not None:
                    out.append(fr)
        return out


# ── .dat parsing helpers ─────────────────────────────────────────────


_QUOTED = re.compile(r'^([^=]+)="(.*)"$')


def _parse_filter_file(path: Path) -> tuple[str, str, list[_DatRule]]:
    if not path.exists():
        return "9", "no", []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.strip().split("\n")
    version = "9"
    logging_val = "no"
    rules: list[_DatRule] = []
    current: _DatRule | None = None
    pending_action: str | None = None
    for line in lines:
        m = _QUOTED.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key == "version":
            version = value
        elif key == "logging":
            logging_val = value
        elif key == "name":
            if current is not None:
                rules.append(current)
            current = _DatRule(name=value)
        elif current is None:
            continue
        elif key == "enabled":
            current.enabled = value
        elif key == "type":
            current.rule_type = value
        elif key == "action":
            pending_action = value
            current.actions.append((value, None))
        elif key == "actionValue":
            if current.actions and pending_action is not None:
                last = current.actions[-1]
                current.actions[-1] = (last[0], value)
        elif key == "condition":
            current.condition = value
    if current is not None:
        rules.append(current)
    return version, logging_val, rules


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.parent / f"{path.name}.backup-{ts}"
    backup.write_bytes(path.read_bytes())
    return backup


def _write_filter_file(
    path: Path,
    version: str,
    logging_val: str,
    rules: list[_DatRule],
) -> None:
    lines = [f'version="{version}"', f'logging="{logging_val}"']
    for r in rules:
        lines.append(r.to_dat())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── domain ↔ .dat translation ────────────────────────────────────────


def _to_dat_rule(rule: FilterRule) -> _DatRule:
    """Translate domain.mail.FilterRule → Thunderbird .dat shape."""
    # Build TB-style condition string. Each from-addr becomes an OR clause.
    clauses = [f"(from,is,{addr})" for addr in rule.condition.from_addrs]
    for s in rule.condition.subject_contains:
        clauses.append(f"(subject,contains,{s})")
    for s in rule.condition.body_contains:
        clauses.append(f"(body,contains,{s})")
    # OR-combined per Thunderbird syntax.
    condition = "OR " + " ".join(clauses) if clauses else ""

    if rule.action.kind == "move":
        # Thunderbird wants imap://... or mailbox://... URI; for now write
        # the folder as-is and let the operator paste a URI in if needed.
        actions = [("Move to folder", rule.action.target)]
    elif rule.action.kind == "tag":
        actions = [("AddTag", rule.action.target)]
    elif rule.action.kind == "flag":
        actions = [("Mark flagged", None)]
    elif rule.action.kind == "delete":
        actions = [("Delete", None)]
    else:
        actions = []
    return _DatRule(name=rule.name, condition=condition, actions=actions)


def _from_dat_rule(dr: _DatRule) -> FilterRule | None:
    """Translate Thunderbird .dat shape → domain.mail.FilterRule.

    Best-effort. Returns None if the dat shape doesn't map cleanly.
    """
    # Parse condition string: "OR (from,is,a@b) (subject,contains,foo)"
    from_addrs: list[str] = []
    subj_parts: list[str] = []
    body_parts: list[str] = []
    for clause in re.findall(r"\(([^)]+)\)", dr.condition):
        parts = clause.split(",", 2)
        if len(parts) < 3:
            continue
        field_, op, val = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if field_.lower() == "from" and op == "is":
            from_addrs.append(val)
        elif field_.lower() == "subject" and op == "contains":
            subj_parts.append(val)
        elif field_.lower() == "body" and op == "contains":
            body_parts.append(val)

    if not dr.actions:
        return None
    action_label, value = dr.actions[0]
    if action_label == "Move to folder":
        action = FilterAction(kind="move", target=value or "")
    elif action_label == "AddTag":
        action = FilterAction(kind="tag", target=value or "")
    elif action_label == "Mark flagged":
        action = FilterAction(kind="flag", target="")
    elif action_label == "Delete":
        action = FilterAction(kind="delete", target="")
    else:
        return None
    return FilterRule(
        name=dr.name,
        condition=FilterCondition(
            from_addrs=tuple(from_addrs),
            subject_contains=tuple(subj_parts),
            body_contains=tuple(body_parts),
        ),
        action=action,
    )
