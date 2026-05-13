"""All-Inkl Webmail Procmail filter — server-side rules via reverse-engineered API.

Filter creation hits the All-Inkl Webmail Procmail endpoint. Rules apply
**immediately** server-side — no Thunderbird restart needed (vs.
ThunderbirdMsgFilter which requires a TB restart).

GOTCHA preserved from `.ytstack/KNOWLEDGE.md`: the `exec-pref-procmail-save`
endpoint is destructive when called with an empty body. Ports the legacy
"backup-before-write" discipline: every save first reads the existing
config and snapshots it to disk, so a botched call is recoverable.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

from adapters.mailbox.base import ApplyResult
from core.config import RAW_DIR
from domain.mail import FilterRule

log = logging.getLogger(__name__)


_BASE = "https://webmail.all-inkl.com"


class AllInklProcmailFilter:
    """Apply mail rules via All-Inkl's webmail procmail endpoint.

    Login uses the account's email (top-level `account.email`) and the
    password from `account.filter.imap_pass_env` (env-var name).
    """

    def __init__(
        self,
        account_id: str,
        email_addr: str,
        imap_pass_env: str,
    ) -> None:
        self._account_id = account_id
        self._email = email_addr
        self._pass_env = imap_pass_env

    def apply(self, rule: FilterRule, *, dry_run: bool = False) -> ApplyResult:
        passwd = os.environ.get(self._pass_env, "") if self._pass_env else ""
        if not passwd or not self._email:
            return ApplyResult(
                success=False,
                message=(
                    f"all-inkl-procmail: missing credentials for {self._account_id} "
                    f"(set ${self._pass_env} and account.email)"
                ),
                dry_run=dry_run,
            )

        try:
            with httpx.Client(timeout=30.0, base_url=_BASE) as client:
                wid, rt = _login(client, self._email, passwd)
                current = _get_procmail(client, wid, rt)
                snippet = _rule_to_procmail(rule)

                if dry_run:
                    return ApplyResult(
                        success=True,
                        message=(
                            f"all-inkl-procmail: would append {len(snippet)} chars "
                            f"to existing config ({len(current)} chars)"
                        ),
                        dry_run=True,
                    )

                # Backup BEFORE save — see KNOWLEDGE.md gotcha.
                _backup(current, self._account_id)
                new_config = current.rstrip() + "\n\n" + snippet + "\n"
                _save_procmail(client, wid, rt, new_config)
                return ApplyResult(
                    success=True,
                    rule_id=rule.name,
                    message=(
                        f"all-inkl-procmail: rule {rule.name!r} appended "
                        f"({len(new_config)} chars total). Active immediately."
                    ),
                )
        except Exception as e:  # noqa: BLE001
            log.exception("AllInklProcmailFilter.apply failed for %s", self._account_id)
            return ApplyResult(
                success=False,
                message=f"all-inkl-procmail: {type(e).__name__}: {e}",
                dry_run=dry_run,
            )

    def list_existing(self) -> list[FilterRule]:
        # Procmail config is freeform text — no structured listing.
        # Returning empty avoids fake dedup; operator audits via webmail UI.
        return []


# ── Internal — webmail API client ────────────────────────────────────


def _login(client: httpx.Client, login_name: str, passwd: str) -> tuple[str, str]:
    resp = client.post(
        "/",
        data={
            "login_target": "desktop",
            "login_name": login_name,
            "login_password": passwd,
        },
    )
    wid_match = re.search(r'INDEX_GLOBAL_WID = "([^"]+)"', resp.text)
    rt_match = re.search(r'INDEX_GLOBAL_RT = "([^"]+)"', resp.text)
    if not wid_match or not rt_match:
        raise RuntimeError("All-Inkl webmail login failed")
    return wid_match.group(1), rt_match.group(1)


def _get_procmail(client: httpx.Client, wid: str, rt: str) -> str:
    r = client.post(
        "/ajax.php",
        data={"a": "data-pref-procmail", "WID": wid, "RT": rt},
    )
    return r.json().get("data", "")


def _save_procmail(client: httpx.Client, wid: str, rt: str, config: str) -> None:
    r = client.post(
        "/ajax.php",
        data={
            "a": "exec-pref-procmail-save",
            "procmail": config,
            "WID": wid,
            "RT": rt,
        },
    )
    result = r.json()
    if not result.get("result"):
        raise RuntimeError(f"procmail save failed: {result.get('msg', 'unknown error')}")


def _backup(current: str, account_id: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = RAW_DIR / "notes" / "email" / f"procmail-backup-{account_id}-{ts}.txt"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(current, encoding="utf-8")
    return backup_path


# ── Domain → procmail snippet translation ────────────────────────────


def _rule_to_procmail(rule: FilterRule) -> str:
    """Translate a domain.mail.FilterRule → procmail recipe block.

    Procmail recipe shape (subset):
        # rule: <name>
        :0:
        * ^From:.*(addr1|addr2)
        .Folder.Subfolder/

    For move actions only — tag/flag/delete don't translate to procmail
    cleanly (procmail can deliver to folders or duplicate; tagging is
    not native).
    """
    if rule.action.kind != "move":
        raise ValueError(
            f"all-inkl-procmail does not support action.kind={rule.action.kind!r} "
            "(move only — tag/flag/delete are not native to procmail)."
        )

    conditions: list[str] = []
    if rule.condition.from_addrs:
        pattern = "|".join(re.escape(a) for a in rule.condition.from_addrs)
        conditions.append(f"* ^From:.*({pattern})")
    if rule.condition.subject_contains:
        pattern = "|".join(re.escape(s) for s in rule.condition.subject_contains)
        conditions.append(f"* ^Subject:.*({pattern})")
    if rule.condition.body_contains:
        # Procmail body matches need 'B' flag — keep simple: skip for now.
        for s in rule.condition.body_contains:
            conditions.append(f"# (body match {s!r} not yet supported)")

    # Procmail folder paths use '.' as separator, leading dot.
    target = rule.action.target
    if not target.startswith("."):
        target = "." + target.replace("/", ".")

    block = [
        f"# rule: {rule.name}",
        ":0:",
    ]
    block.extend(conditions)
    block.append(f"{target}/")
    return "\n".join(block)
