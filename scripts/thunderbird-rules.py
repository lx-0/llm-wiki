"""
Thunderbird filter rules — parse, list, create, export, and execute via IMAP.

Two execution paths:
- msgFilterRules.dat: Create/modify rules for FUTURE mails (TB must be closed)
- IMAP direct: Move/tag/flag EXISTING mails via imapclient (TB can be open)

Usage:
    uv run python scripts/thunderbird-rules.py --list
    uv run python scripts/thunderbird-rules.py --list --account work
    uv run python scripts/thunderbird-rules.py --add --name "Sort invoices" --condition 'AND (from,is,billing@example.com)' --action "Move to folder" --action-value "INBOX/Sorted/Bills" --account work
    uv run python scripts/thunderbird-rules.py --execute "invoices: business" --folder INBOX --dry-run
    uv run python scripts/thunderbird-rules.py --export
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from config import RAW_DIR, ROOT_DIR
from wiki_config import CONFIG

load_dotenv(ROOT_DIR / ".claude" / ".env")

# ── Thunderbird profile ─────────────────────────────────────────────

_TB_PROFILE_RAW = CONFIG.personal.thunderbird_profile
THUNDERBIRD_PROFILE = (
    Path(_TB_PROFILE_RAW).expanduser() if _TB_PROFILE_RAW else Path()
)


def _build_accounts() -> dict[str, dict]:
    """Materialise CONFIG.personal.accounts into runtime form for this script.

    Resolves filter_paths relative to thunderbird_profile and surfaces
    only the fields this script consumes.
    """
    out: dict[str, dict] = {}
    for aid, info in CONFIG.personal.accounts.items():
        out[aid] = {
            "filter_paths": [THUNDERBIRD_PROFILE / p for p in info.get("filter_paths", [])],
            "imap_host": info.get("imap_host", ""),
            "imap_user_env": info.get("imap_user_env", ""),
            "imap_pass_env": info.get("imap_pass_env", ""),
            "email": info.get("email", ""),
        }
    return out


ACCOUNTS = _build_accounts()

# ── Rule dataclass ──────────────────────────────────────────────────


@dataclass
class FilterRule:
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

    def summary(self) -> str:
        acts = []
        for action, value in self.actions:
            if value:
                acts.append(f"{action} → {value}")
            else:
                acts.append(action)
        return f"[{'ON' if self.enabled == 'yes' else 'OFF'}] {self.name}: {self.condition} => {', '.join(acts)}"


# ── Parser ──────────────────────────────────────────────────────────


def parse_filter_file(path: Path) -> tuple[str, str, list[FilterRule]]:
    """Parse a msgFilterRules.dat file. Returns (version, logging, rules)."""
    if not path.exists():
        return "9", "no", []

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.strip().split("\n")

    version = "9"
    logging_val = "no"
    rules: list[FilterRule] = []
    current: FilterRule | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = re.match(r'^(\w+)="(.*)"$', line)
        if not match:
            continue

        key, val = match.group(1), match.group(2)

        if key == "version":
            version = val
        elif key == "logging":
            logging_val = val
        elif key == "name":
            if current is not None:
                rules.append(current)
            current = FilterRule(name=val)
        elif current is not None:
            if key == "enabled":
                current.enabled = val
            elif key == "type":
                current.rule_type = val
            elif key == "action":
                current.actions.append((val, None))
            elif key == "actionValue" and current.actions:
                act, _ = current.actions[-1]
                current.actions[-1] = (act, val)
            elif key == "condition":
                current.condition = val

    if current is not None:
        rules.append(current)

    return version, logging_val, rules


def backup_filter_file(path: Path) -> Path | None:
    """Create a timestamped backup of msgFilterRules.dat before modifying."""
    if not path.exists():
        return None
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.parent / f"msgFilterRules.dat.backup-{ts}"
    backup.write_bytes(path.read_bytes())
    return backup


def find_overlapping_rules(account_id: str, condition: str) -> list[tuple[str, FilterRule]]:
    """Check if any existing rule already covers (parts of) this condition.

    Extracts values from condition clauses and checks if they appear
    in any existing rule's condition. Returns list of (filter_path, rule) matches.
    """
    # Extract match values from the proposed condition
    clauses = re.findall(r'\(([^)]+)\)', condition)
    proposed_values = set()
    for clause in clauses:
        parts = clause.split(",", 2)
        if len(parts) >= 3:
            proposed_values.add(parts[2].strip().lower())

    if not proposed_values:
        return []

    acct = ACCOUNTS.get(account_id, {})
    overlaps = []
    for fp in acct.get("filter_paths", []):
        if not fp.exists():
            continue
        _, _, rules = parse_filter_file(fp)
        for rule in rules:
            existing_clauses = re.findall(r'\(([^)]+)\)', rule.condition)
            for clause in existing_clauses:
                parts = clause.split(",", 2)
                if len(parts) >= 3 and parts[2].strip().lower() in proposed_values:
                    overlaps.append((str(fp), rule))
                    break

    return overlaps


def validate_new_rule(account_id: str, condition: str) -> tuple[bool, str]:
    """Validate that a proposed rule doesn't duplicate existing rules.

    Returns (is_valid, reason). Call this BEFORE creating a suggestion.
    The compiler must call this to filter duplicates at generation time.
    """
    overlaps = find_overlapping_rules(account_id, condition)
    if overlaps:
        names = ", ".join(f"'{r.name}'" for _, r in overlaps)
        return False, f"Already covered by: {names}"
    return True, ""


def write_filter_file(path: Path, version: str, logging_val: str, rules: list[FilterRule]) -> None:
    """Write rules back to msgFilterRules.dat. Creates a backup first."""
    backup = backup_filter_file(path)
    if backup:
        print(f"  Backup: {backup}")
    lines = [f'version="{version}"', f'logging="{logging_val}"']
    for rule in rules:
        lines.append(rule.to_dat())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── IMAP execution ──────────────────────────────────────────────────


def condition_to_imap_search(condition: str) -> list[str]:
    """Convert a Thunderbird condition string to IMAP SEARCH criteria."""
    clauses = re.findall(r'\(([^)]+)\)', condition)
    if not clauses:
        return ["ALL"]

    is_or = condition.strip().startswith("OR")

    criteria: list[list[str]] = []
    for clause in clauses:
        parts = clause.split(",", 2)
        if len(parts) < 3:
            continue
        header, operator, value = parts[0].strip().strip('"'), parts[1].strip(), parts[2].strip()

        header_map = {
            "from": "FROM", "subject": "SUBJECT", "to": "TO",
            "cc": "CC", "to or cc": "TO", "sender": "FROM",
        }
        imap_header = header_map.get(header.lower(), "FROM")

        if operator in ("is", "contains", "begins with", "ends with"):
            criteria.append([imap_header, value])
        elif operator == "isn't":
            criteria.append(["NOT", imap_header, value])

    if not criteria:
        return ["ALL"]

    if is_or and len(criteria) > 1:
        result = criteria[0]
        for c in criteria[1:]:
            result = ["OR"] + result + c
        return result

    result = []
    for c in criteria:
        result.extend(c)
    return result


def _get_gmail_credentials(account_id: str):
    """Get Gmail OAuth2 credentials. Opens browser on first run.

    Uses pickle for token storage as required by google-auth library.
    These are our own locally-generated OAuth tokens, not untrusted data.
    """
    import pickle  # noqa: S403 — own OAuth tokens, not untrusted data
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_file = ROOT_DIR / ".claude" / f"gmail-token-{account_id}.pickle"
    client_secret = ROOT_DIR / ".claude" / "gmail-oauth-client.json"
    scopes = ["https://mail.google.com/", "https://www.googleapis.com/auth/gmail.settings.basic"]

    creds = None
    if token_file.exists():
        with open(token_file, "rb") as f:
            creds = pickle.load(f)  # noqa: S301

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret.exists():
                return None, f"Gmail OAuth client config not found: {client_secret}"
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes)
            print(f"  Opening browser for Gmail OAuth2 login ({account_id})...")
            creds = flow.run_local_server(port=0)

        with open(token_file, "wb") as f:
            pickle.dump(creds, f)  # noqa: S301

    return creds, None


def _get_imap_client(account_id: str):
    """Connect to IMAP server for an account. Returns (client, error_msg).

    Gmail accounts use OAuth2 (browser login on first use, then auto-refresh).
    Other accounts use password from .env.
    """
    from imapclient import IMAPClient

    acct = ACCOUNTS.get(account_id)
    if not acct:
        return None, f"Unknown account: {account_id}"

    host = acct.get("imap_host")
    if not host:
        return None, f"No IMAP host configured for {account_id}"

    client = IMAPClient(host, ssl=True)

    # Gmail: OAuth2
    if "gmail" in host:
        email = acct.get("email", "")
        if not email:
            return None, f"No email configured for {account_id}"
        creds, error = _get_gmail_credentials(account_id)
        if error:
            return None, error
        client.oauth2_login(email, creds.token)
    else:
        # Password auth
        user = os.environ.get(acct["imap_user_env"], "")
        passwd = os.environ.get(acct["imap_pass_env"], "")
        if not user or not passwd:
            return None, f"IMAP credentials not set: {acct['imap_user_env']}, {acct['imap_pass_env']} in .claude/.env"
        client.login(user, passwd)

    return client, None


def execute_rule_imap(account_id: str, rule: FilterRule, folder: str, dry_run: bool = True) -> dict:
    """Execute a filter rule on a folder via IMAP. Returns stats."""
    stats = {"matched": 0, "actions": [], "dry_run": dry_run}

    if dry_run:
        search_criteria = condition_to_imap_search(rule.condition)
        print(f"  [dry-run] IMAP search on {folder}: {search_criteria}")
        for action, value in rule.actions:
            print(f"  [dry-run] Would: {action}" + (f" → {_extract_folder_path(value)}" if value else ""))
        stats["matched"] = -1  # unknown without connection
        return stats

    client, error = _get_imap_client(account_id)
    if error:
        print(f"  {error}")
        return {"error": error}

    search_criteria = condition_to_imap_search(rule.condition)

    try:
        client.select_folder(folder)
        uids = client.search(search_criteria)
        stats["matched"] = len(uids)

        if not uids:
            print(f"  No matching messages in {folder}")
            return stats

        print(f"  Found {len(uids)} matching messages in {folder}")

        for action, value in rule.actions:
            _execute_imap_action(client, uids, action, value, stats)
    finally:
        client.logout()

    return stats


def _ensure_folder_exists(client, target: str) -> None:
    """Create IMAP folder if it doesn't exist."""
    existing = [name for _, _, name in client.list_folders()]
    if target not in existing:
        print(f"    Creating folder '{target}'...")
        client.create_folder(target)


def imap_move(account_id: str, folder: str, search: list, target: str, dry_run: bool = True) -> dict:
    """Move specific mails via IMAP search. For individual mail operations."""
    stats = {"matched": 0, "actions": [], "dry_run": dry_run}
    if dry_run:
        print(f"    [dry-run] IMAP search on {folder}: {search}")
        print(f"    [dry-run] Would move matching mails to {target}")
        return stats

    client, error = _get_imap_client(account_id)
    if error:
        print(f"  {error}")
        return {"error": error}
    try:
        _ensure_folder_exists(client, target)
        client.select_folder(folder)
        uids = client.search(search)
        stats["matched"] = len(uids)
        if not uids:
            print(f"  No matching messages in {folder}")
            return stats
        client.move(uids, target)
        stats["actions"].append(f"Moved {len(uids)} to {target}")
        print(f"  Moved {len(uids)} messages to {target}")
    finally:
        client.logout()
    return stats


def imap_tag(account_id: str, folder: str, search: list, tag: str, dry_run: bool = True) -> dict:
    """Tag specific mails via IMAP."""
    stats = {"matched": 0, "actions": [], "dry_run": dry_run}
    if dry_run:
        print(f"    [dry-run] IMAP search on {folder}: {search}")
        print(f"    [dry-run] Would tag matching mails with {tag}")
        return stats

    client, error = _get_imap_client(account_id)
    if error:
        print(f"  {error}")
        return {"error": error}
    try:
        client.select_folder(folder)
        uids = client.search(search)
        stats["matched"] = len(uids)
        if not uids:
            print(f"  No matching messages in {folder}")
            return stats
        client.add_flags(uids, [tag.encode()])
        stats["actions"].append(f"Tagged {len(uids)} with {tag}")
        print(f"  Tagged {len(uids)} with {tag}")
    finally:
        client.logout()
    return stats


def imap_set_flags(account_id: str, folder: str, search: list, flags: list[str], dry_run: bool = True) -> dict:
    """Set flags (seen, flagged, etc) on specific mails via IMAP."""
    stats = {"matched": 0, "actions": [], "dry_run": dry_run}
    if dry_run:
        print(f"    [dry-run] IMAP search on {folder}: {search}")
        print(f"    [dry-run] Would set flags {flags} on matching mails")
        return stats

    client, error = _get_imap_client(account_id)
    if error:
        print(f"  {error}")
        return {"error": error}
    try:
        client.select_folder(folder)
        uids = client.search(search)
        stats["matched"] = len(uids)
        if not uids:
            print(f"  No matching messages in {folder}")
            return stats
        imap_flags = [f.encode() for f in flags]
        client.add_flags(uids, imap_flags)
        stats["actions"].append(f"Set {flags} on {len(uids)}")
        print(f"  Set flags {flags} on {len(uids)} messages")
    finally:
        client.logout()
    return stats


def _execute_imap_action(client, uids: list, action: str, value: str | None, stats: dict) -> None:
    """Execute a single TB filter action via IMAP."""
    if action == "Move to folder" and value:
        target = _extract_folder_path(value)
        client.move(uids, target)
        stats["actions"].append(f"Moved {len(uids)} to {target}")
        print(f"  Moved {len(uids)} messages to {target}")
    elif action == "Copy to folder" and value:
        target = _extract_folder_path(value)
        client.copy(uids, target)
        stats["actions"].append(f"Copied {len(uids)} to {target}")
        print(f"  Copied {len(uids)} messages to {target}")
    elif action == "Mark read":
        client.add_flags(uids, [b"\\Seen"])
        stats["actions"].append(f"Marked {len(uids)} as read")
        print(f"  Marked {len(uids)} as read")
    elif action == "Mark flagged":
        client.add_flags(uids, [b"\\Flagged"])
        stats["actions"].append(f"Flagged {len(uids)}")
        print(f"  Flagged {len(uids)} messages")
    elif action == "Mark unread":
        client.remove_flags(uids, [b"\\Seen"])
        stats["actions"].append(f"Marked {len(uids)} as unread")
    elif action == "AddTag" and value:
        client.add_flags(uids, [value.encode()])
        stats["actions"].append(f"Tagged {len(uids)} with {value}")
        print(f"  Tagged {len(uids)} with {value}")
    elif action == "JunkScore" and value:
        flag = b"Junk" if value == "100" else b"NonJunk"
        client.add_flags(uids, [flag])
        stats["actions"].append(f"Set junk={value} on {len(uids)}")
    elif action == "Delete":
        client.add_flags(uids, [b"\\Deleted"])
        client.expunge()
        stats["actions"].append(f"Deleted {len(uids)}")
        print(f"  Deleted {len(uids)} messages")


def _extract_folder_path(uri_or_path: str) -> str:
    """Extract folder path from Thunderbird IMAP URI or plain path."""
    if uri_or_path.startswith("imap://"):
        parts = uri_or_path.split("/", 3)
        if len(parts) >= 4:
            return parts[3]
    return uri_or_path


# ── Gmail filters (API) ─────────────────────────────────────────────


def _gmail_session(account_id: str):
    """Get an authorized Gmail API session. Returns (session, error)."""
    from google.auth.transport.requests import AuthorizedSession
    creds, error = _get_gmail_credentials(account_id)
    if error:
        return None, error
    return AuthorizedSession(creds), None


def list_gmail_filters(account_id: str) -> list[dict]:
    """List all Gmail filters via API."""
    session, error = _gmail_session(account_id)
    if error:
        print(f"  {error}")
        return []
    resp = session.get("https://gmail.googleapis.com/gmail/v1/users/me/settings/filters")
    if resp.status_code == 204:
        return []
    return resp.json().get("filter", [])


def _get_gmail_label_id(session, label_name: str) -> str | None:
    """Find or create a Gmail label, return its ID."""
    resp = session.get("https://gmail.googleapis.com/gmail/v1/users/me/labels")
    for label in resp.json().get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    # Create it
    resp = session.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        json={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    )
    if resp.status_code == 200:
        return resp.json()["id"]
    return None


def create_gmail_filter(account_id: str, from_addresses: list[str], label_name: str,
                        remove_from_inbox: bool = True, dry_run: bool = True) -> dict:
    """Create a Gmail filter via API."""
    stats = {"created": False, "dry_run": dry_run}

    session, error = _gmail_session(account_id)
    if error:
        return {"error": error}

    label_id = _get_gmail_label_id(session, label_name)
    if not label_id:
        return {"error": f"Could not find/create label '{label_name}'"}

    from_criteria = " OR ".join(from_addresses)
    action = {"addLabelIds": [label_id]}
    if remove_from_inbox:
        action["removeLabelIds"] = ["INBOX"]

    filter_body = {"criteria": {"from": from_criteria}, "action": action}

    if dry_run:
        import json
        print(f"    [dry-run] Would create Gmail filter:")
        print(f"    {json.dumps(filter_body, indent=6)}")
        return stats

    resp = session.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/settings/filters",
        json=filter_body,
    )
    if resp.status_code == 200:
        stats["created"] = True
        stats["filter_id"] = resp.json().get("id")
        print(f"    Created Gmail filter: {from_criteria} → {label_name}")
    else:
        stats["error"] = f"Gmail API error {resp.status_code}: {resp.text}"
        print(f"    ERROR: {stats['error']}")

    return stats


def is_gmail_account(account_id: str) -> bool:
    """Check if an account uses Gmail (OAuth2) vs password auth."""
    acct = ACCOUNTS.get(account_id, {})
    return "gmail" in acct.get("imap_host", "")


# ── All-Inkl Webmail Procmail API ────────────────────────────────────


def _webmail_session():
    """Login to All-Inkl webmail and return (session, wid, rt) or (None, None, error)."""
    import requests as req

    primary = CONFIG.personal.primary_account
    primary_info = CONFIG.personal.accounts.get(primary, {})
    user_env = primary_info.get("imap_user_env", "")
    pass_env = primary_info.get("imap_pass_env", "")
    login_name = primary_info.get("email", "")
    passwd = os.environ.get(pass_env, "") if pass_env else ""
    if not passwd or not login_name:
        return None, None, (
            f"Webmail credentials missing: set personal.primary_account, its email, "
            f"and {pass_env or '<imap_pass_env>'} in .claude/.env"
        )

    session = req.Session()
    resp = session.post("https://webmail.all-inkl.com/", data={
        "login_target": "desktop",
        "login_name": login_name,
        "login_password": passwd,
    })

    wid_match = re.search(r'INDEX_GLOBAL_WID = "([^"]+)"', resp.text)
    rt_match = re.search(r'INDEX_GLOBAL_RT = "([^"]+)"', resp.text)
    if not wid_match or not rt_match:
        return None, None, "Webmail login failed"

    wid = wid_match.group(1)
    rt = rt_match.group(1)
    return session, wid, rt


def get_procmail_config() -> str:
    """Read current procmail config from All-Inkl webmail."""
    session, wid, rt = _webmail_session()
    if not session:
        print(f"  {rt}")  # rt contains error message
        return ""

    r = session.post("https://webmail.all-inkl.com/ajax.php", data={
        "a": "data-pref-procmail",
        "WID": wid, "RT": rt,
    })
    return r.json().get("data", "")


def save_procmail_config(config: str, dry_run: bool = True) -> bool:
    """Save procmail config to All-Inkl webmail. Creates backup first."""
    session, wid, rt = _webmail_session()
    if not session:
        print(f"  {rt}")
        return False

    # Backup current config
    r = session.post("https://webmail.all-inkl.com/ajax.php", data={
        "a": "data-pref-procmail",
        "WID": wid, "RT": rt,
    })
    current = r.json().get("data", "")

    if dry_run:
        print(f"    [dry-run] Current procmail: {len(current)} chars")
        print(f"    [dry-run] New procmail: {len(config)} chars")
        return True

    # Save backup locally
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = ROOT_DIR / "raw" / "notes" / "email" / f"procmail-backup-{ts}.txt"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(current, encoding="utf-8")
    print(f"    Backup: {backup_path}")

    # Save new config
    r2 = session.post("https://webmail.all-inkl.com/ajax.php", data={
        "a": "exec-pref-procmail-save",
        "procmail": config,
        "WID": wid, "RT": rt,
    })
    result = r2.json()
    if result.get("result"):
        print(f"    Procmail saved ({len(config)} chars)")
        return True
    else:
        print(f"    ERROR: {result.get('msg', 'unknown error')}")
        return False


def add_procmail_rule(name: str, condition: str, folder: str, dry_run: bool = True) -> bool:
    """Add a single rule to the procmail config.

    Converts a Thunderbird-style condition to procmail syntax and appends it.
    """
    # Parse TB condition to procmail
    clauses = re.findall(r'\(([^)]+)\)', condition)
    from_addresses = []
    subject_patterns = []

    for clause in clauses:
        parts = clause.split(",", 2)
        if len(parts) < 3:
            continue
        header, op, val = parts[0].strip().strip('"'), parts[1].strip(), parts[2].strip()

        if "from" in header.lower():
            from_addresses.append(re.escape(val).replace(r"\+", r"\+"))
        elif "subject" in header.lower():
            subject_patterns.append(val)

    if not from_addresses and not subject_patterns:
        print(f"    Cannot convert condition to procmail: {condition}")
        return False

    # Build procmail rule
    lines = [f"\n\n### {name} ###"]
    if from_addresses:
        pattern = "|".join(from_addresses)
        lines.append(":0 w")
        lines.append(f"* ^From:.*({pattern})")
        lines.append(f'| $DELIVER -m "{folder}"')
    if subject_patterns:
        for subj in subject_patterns:
            lines.append(":0 w")
            lines.append(f"* ^Subject:.*{re.escape(subj)}")
            lines.append(f'| $DELIVER -m "{folder}"')

    new_rule = "\n".join(lines)

    # Get current config and append
    current = get_procmail_config()

    if dry_run:
        print(f"    [dry-run] Would append to procmail ({len(current)} chars):")
        print(f"    {new_rule}")
        return True

    updated = current.rstrip() + "\n" + new_rule + "\n"
    return save_procmail_config(updated, dry_run=False)


def has_procmail_support(account_id: str) -> bool:
    """Check if an account uses All-Inkl webmail (procmail) for server-side rules.

    Driven by `personal.accounts.<id>.has_procmail: true` in config.yaml
    (only the All-Inkl kasserver account currently exposes this surface).
    """
    return bool(CONFIG.personal.accounts.get(account_id, {}).get("has_procmail"))


# ── Export to raw/notes ─────────────────────────────────────────────


def export_rules_overview() -> Path:
    """Export all Thunderbird rules to raw/notes/email/thunderbird-rules-overview.md."""
    from config import today_iso

    report_dir = RAW_DIR / "notes" / "email"
    report_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        "type: note",
        f"date: {today_iso()}",
        "origin: scan-thunderbird-rules",
        "tags: [thunderbird, email-rules, metadata]",
        "language: de",
        "---",
        "",
        "# Thunderbird Filter Rules Overview",
        "",
    ]

    total_rules = 0

    for account_id, acct in ACCOUNTS.items():
        lines.append(f"## Account: {account_id}")
        lines.append("")

        for filter_path in acct["filter_paths"]:
            if not filter_path.exists():
                continue

            version, _, rules = parse_filter_file(filter_path)
            total_rules += len(rules)

            lines.append(f"### {filter_path.parent.name} ({len(rules)} rules, version {version})")
            lines.append("")

            if not rules:
                lines.append("*No rules.*")
                lines.append("")
                continue

            lines.append("| # | Name | Enabled | Condition | Actions |")
            lines.append("|---|------|---------|-----------|---------|")

            for i, rule in enumerate(rules, 1):
                acts = "; ".join(
                    f"{a}" + (f"→{v}" if v else "") for a, v in rule.actions
                )
                lines.append(f"| {i} | {rule.name} | {rule.enabled} | `{rule.condition}` | {acts} |")

            lines.append("")

    lines.append(f"**Total: {total_rules} rules across all accounts.**")

    out_path = report_dir / "thunderbird-rules-overview.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── CLI ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Thunderbird filter rules manager")
    parser.add_argument("--list", action="store_true", help="List all rules")
    parser.add_argument("--account", type=str, help="Filter by account id from CONFIG.personal.accounts (e.g. work, gmail-personal)")
    parser.add_argument("--execute", type=str, metavar="RULE_NAME", help="Execute a rule retroactively via IMAP")
    parser.add_argument("--folder", type=str, default="INBOX", help="IMAP folder for --execute (default: INBOX)")
    parser.add_argument("--add", action="store_true", help="Add a new rule to msgFilterRules.dat")
    parser.add_argument("--name", type=str, help="Rule name for --add")
    parser.add_argument("--condition", type=str, help="Condition for --add")
    parser.add_argument("--action", type=str, help="Action for --add (e.g. 'Move to folder')")
    parser.add_argument("--action-value", type=str, help="Action value for --add (e.g. folder URI)")
    parser.add_argument("--export", action="store_true", help="Export rules to raw/notes/email/")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")

    args = parser.parse_args()

    accounts = ACCOUNTS
    if args.account:
        if args.account not in ACCOUNTS:
            print(f"Unknown account: {args.account}. Available: {', '.join(ACCOUNTS)}")
            sys.exit(1)
        accounts = {args.account: ACCOUNTS[args.account]}

    # ── List ──
    if args.list:
        for account_id, acct in accounts.items():
            print(f"\n{'=' * 60}")
            print(f"Account: {account_id}")
            print(f"{'=' * 60}")
            for filter_path in acct["filter_paths"]:
                if not filter_path.exists():
                    continue
                _, _, rules = parse_filter_file(filter_path)
                print(f"\n  {filter_path.parent.name}/ ({len(rules)} rules):")
                for rule in rules:
                    print(f"    {rule.summary()}")
        return

    # ── Execute rule via IMAP ──
    if args.execute:
        rule_name = args.execute
        for account_id, acct in accounts.items():
            for filter_path in acct["filter_paths"]:
                if not filter_path.exists():
                    continue
                _, _, rules = parse_filter_file(filter_path)
                for rule in rules:
                    if rule.name == rule_name:
                        print(f"Executing rule '{rule_name}' on {args.folder} (account: {account_id})")
                        print(f"  Condition: {rule.condition}")
                        for action, value in rule.actions:
                            print(f"  Action: {action}" + (f" → {value}" if value else ""))
                        stats = execute_rule_imap(account_id, rule, args.folder, dry_run=args.dry_run)
                        if "error" in stats:
                            print(f"  Error: {stats['error']}")
                            sys.exit(1)
                        print(f"  Result: {stats['matched']} matched")
                        return
        print(f"Rule '{rule_name}' not found.")
        sys.exit(1)

    # ── Add ──
    if args.add:
        if not args.name or not args.condition or not args.action:
            print("--add requires --name, --condition, --action, and --account")
            sys.exit(1)
        if not args.account or args.account not in ACCOUNTS:
            print("--add requires a single --account")
            sys.exit(1)

        acct = ACCOUNTS[args.account]
        filter_path = next(
            (p for p in acct["filter_paths"] if p.exists()),
            acct["filter_paths"][0],
        )

        version, logging_val, rules = parse_filter_file(filter_path)

        new_rule = FilterRule(
            name=args.name,
            condition=args.condition,
            actions=[(args.action, args.action_value)],
        )

        if args.dry_run:
            print(f"[dry-run] Would add to {filter_path}:")
            print(f"  {new_rule.to_dat()}")
            return

        rules.append(new_rule)
        write_filter_file(filter_path, version, logging_val, rules)
        print(f"Added rule '{args.name}' to {filter_path}")
        print(f"  Total rules now: {len(rules)}")
        print("  NOTE: Thunderbird must be restarted to pick up the change.")

    # ── Export ──
    if args.export:
        out = export_rules_overview()
        print(f"Exported rules overview to {out.relative_to(ROOT_DIR)}")
        return

    if not any([args.list, args.execute, args.add, args.export]):
        parser.print_help()


if __name__ == "__main__":
    main()
