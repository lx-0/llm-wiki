"""
Execute approved optimization suggestions — per-action approval.

Each suggestion file contains multiple actions. Each action has its own status
and must be individually approved before execution.

Usage:
    uv run python scripts/execute-suggestions.py --list                          # show all suggestions + action statuses
    uv run python scripts/execute-suggestions.py --review test-billing           # interactively review each action
    uv run python scripts/execute-suggestions.py --approve test-billing 1        # approve action #1
    uv run python scripts/execute-suggestions.py --reject test-billing 2         # reject action #2
    uv run python scripts/execute-suggestions.py --dry-run                       # preview approved actions
    uv run python scripts/execute-suggestions.py                                 # execute approved actions
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from core.config import RAW_SUGGESTIONS_DIR, ROOT_DIR, TIMEZONE
from core.wiki_config import CONFIG

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.mailbox import resolve_filter
import imap_actions
from domain.mail import FilterAction, FilterCondition, FilterRule


# ── YAML I/O ────────────────────────────────────────────────────────


def load_suggestion(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^---\s*\n", "", text, count=1)
    text = re.sub(r"\n---\s*$", "", text, count=1)
    return yaml.safe_load(text) or {}


def save_suggestion(path: Path, data: dict) -> None:
    path.write_text(
        "---\n" + yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _resolve(name_or_path: str, known: list[Path]) -> Path | None:
    path = Path(name_or_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if path.exists():
        return path
    for f in known:
        if f.name == name_or_path or f.stem == name_or_path:
            return f
    for f in known:
        if name_or_path in f.name:
            return f
    print(f"Not found: {name_or_path}")
    return None


# ── Action display ──────────────────────────────────────────────────


def describe_action(i: int, action: dict) -> None:
    """Print a human-readable description of one action."""
    action_type = action.get("type", "?")
    status = action.get("status", "pending")
    account = action.get("account", CONFIG.personal.primary_account)
    status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌", "executed": "✔️"}.get(status, "?")

    print(f"  Action {i} [{status_icon} {status}]: {action_type} (account: {account})")

    if action_type == "create-rule":
        rule = action.get("rule", {})
        condition = rule.get("condition", "")
        folder = rule.get("folder", "")
        action_label = rule.get("action", "Move to folder")
        account_cfg = (CONFIG.personal.accounts or {}).get(account, {})
        filter_kind = (account_cfg.get("filter") or {}).get("kind", "<unset>")
        print(f"    Account: {account}  Filter kind: {filter_kind}")
        print(f"    Rule:     {rule.get('name', '?')}")
        print(f"    Condition: {condition}")
        print(f"    Action:   {action_label} → {folder}")

    elif action_type == "imap-move":
        print(f"    Search: {action.get('search', [])}")
        print(f"    From: {action.get('source_folder', 'INBOX')} → To: {action.get('target_folder', '?')}")

    elif action_type == "imap-tag":
        print(f"    Search: {action.get('search', [])}")
        print(f"    Folder: {action.get('folder', 'INBOX')}")
        print(f"    Tag: {action.get('tag', '?')}")

    elif action_type == "imap-set-flags":
        print(f"    Search: {action.get('search', [])}")
        print(f"    Folder: {action.get('folder', 'INBOX')}")
        print(f"    Flags: {action.get('flags', [])}")

    print()


# ── Action execution ────────────────────────────────────────────────


def execute_action(action: dict, dry_run: bool = True) -> bool:
    """Execute a single approved action. Returns True on success."""
    action_type = action.get("type", "")
    account_id = action.get("account", CONFIG.personal.primary_account)

    if action_type == "create-rule":
        rule_yaml = action.get("rule", {})
        rule_name = rule_yaml.get("name", "")
        condition_str = rule_yaml.get("condition", "")
        folder = rule_yaml.get("folder", "")

        # Resolve the per-account Filter adapter. None = no kind configured
        # or unknown kind — graceful agnostic, skip with a clear message.
        account = (CONFIG.personal.accounts or {}).get(account_id, {})
        # `_id` is a synthetic field for resolver logging; doesn't touch CONFIG file
        account_with_id = {**account, "_id": account_id}
        filter_adapter = resolve_filter(account_with_id)
        if filter_adapter is None:
            print(f"    SKIP: no filter resolved for account {account_id!r}")
            print(f"    (configure account.filter.kind — see CONTEXT.md § Account.kind)")
            return False

        # Translate the YAML rule to domain.mail.FilterRule.
        rule = _yaml_to_filter_rule(rule_name, condition_str, folder, rule_yaml.get("action", "Move to folder"))

        result = filter_adapter.apply(rule, dry_run=dry_run)
        print(f"    {result.message}")
        return result.success

    elif action_type == "imap-move":
        stats = imap_actions.imap_move(
            account_id,
            action.get("source_folder", "INBOX"),
            action.get("search", []),
            action.get("target_folder", ""),
            dry_run=dry_run,
        )
        return "error" not in stats

    elif action_type == "imap-tag":
        stats = imap_actions.imap_tag(
            account_id,
            action.get("folder", "INBOX"),
            action.get("search", []),
            action.get("tag", ""),
            dry_run=dry_run,
        )
        return "error" not in stats

    elif action_type == "imap-set-flags":
        stats = imap_actions.imap_set_flags(
            account_id,
            action.get("folder", "INBOX"),
            action.get("search", []),
            action.get("flags", []),
            dry_run=dry_run,
        )
        return "error" not in stats

    else:
        print(f"    Unknown action type: {action_type}")
        return False


def _yaml_to_filter_rule(name: str, condition_str: str, folder: str, action_label: str) -> FilterRule:
    """Translate the YAML-suggestion rule shape to domain.mail.FilterRule.

    YAML condition is the legacy TB-style string ('OR (from,is,a@b) (subject,contains,foo)').
    We parse it into the structured FilterCondition.
    """
    import re as _re

    from_addrs: list[str] = []
    subj: list[str] = []
    body: list[str] = []
    for clause in _re.findall(r"\(([^)]+)\)", condition_str):
        parts = clause.split(",", 2)
        if len(parts) < 3:
            continue
        field_, op, val = parts[0].strip().lower(), parts[1].strip(), parts[2].strip()
        if field_ == "from" and op == "is":
            from_addrs.append(val)
        elif field_ == "subject" and op == "contains":
            subj.append(val)
        elif field_ == "body" and op == "contains":
            body.append(val)

    # Action mapping: "Move to folder" → move; AddTag/Mark flagged/Delete handled too.
    action_label_lower = action_label.lower()
    if "move" in action_label_lower:
        action = FilterAction(kind="move", target=folder)
    elif "tag" in action_label_lower:
        action = FilterAction(kind="tag", target=folder)
    elif "flag" in action_label_lower:
        action = FilterAction(kind="flag", target="")
    elif "delete" in action_label_lower:
        action = FilterAction(kind="delete", target="")
    else:
        action = FilterAction(kind="move", target=folder)

    return FilterRule(
        name=name,
        condition=FilterCondition(
            from_addrs=tuple(from_addrs),
            subject_contains=tuple(subj),
            body_contains=tuple(body),
        ),
        action=action,
    )


# ── CLI ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute optimization suggestions — per-action approval",
        epilog="Each action within a suggestion is approved/rejected individually.",
    )
    parser.add_argument("--list", action="store_true", help="List all suggestions with per-action status")
    parser.add_argument("--review", type=str, metavar="FILE", help="Interactively review each action in a suggestion")
    parser.add_argument("--approve", type=str, metavar="FILE", help="Approve an action (requires action number)")
    parser.add_argument("--reject", type=str, metavar="FILE", help="Reject an action (requires action number)")
    parser.add_argument("action_num", nargs="?", type=int, help="Action number for --approve/--reject (1-based)")
    parser.add_argument("--dry-run", action="store_true", help="Preview approved actions without executing")
    args = parser.parse_args()

    RAW_SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    suggestion_files = sorted(RAW_SUGGESTIONS_DIR.glob("*.yaml")) + sorted(RAW_SUGGESTIONS_DIR.glob("*.yml"))

    if not suggestion_files:
        print("No suggestions in raw/suggestions/")
        return

    # ── List ──
    if args.list:
        for f in suggestion_files:
            data = load_suggestion(f)
            print(f"\n{'=' * 60}")
            print(f"File: {f.name}")
            print(f"Target: {data.get('target', '?')}")
            print(f"Rationale: {data.get('rationale', '')}")
            for i, action in enumerate(data.get("actions", []), 1):
                describe_action(i, action)
        return

    # ── Approve action ──
    if args.approve:
        if not args.action_num:
            print("Usage: --approve <file> <action_number>")
            print("Example: --approve test-billing 1")
            sys.exit(1)
        path = _resolve(args.approve, suggestion_files)
        if not path:
            sys.exit(1)
        data = load_suggestion(path)
        actions = data.get("actions", [])
        idx = args.action_num - 1
        if idx < 0 or idx >= len(actions):
            print(f"Action {args.action_num} not found (file has {len(actions)} actions)")
            sys.exit(1)
        if actions[idx].get("status", "pending") != "pending":
            print(f"Action {args.action_num} is already '{actions[idx].get('status')}'")
            sys.exit(1)
        actions[idx]["status"] = "approved"
        actions[idx]["reviewed"] = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
        save_suggestion(path, data)
        print(f"Approved action {args.action_num} in {path.name}:")
        describe_action(args.action_num, actions[idx])
        return

    # ── Reject action ──
    if args.reject:
        if not args.action_num:
            print("Usage: --reject <file> <action_number>")
            sys.exit(1)
        path = _resolve(args.reject, suggestion_files)
        if not path:
            sys.exit(1)
        data = load_suggestion(path)
        actions = data.get("actions", [])
        idx = args.action_num - 1
        if idx < 0 or idx >= len(actions):
            print(f"Action {args.action_num} not found (file has {len(actions)} actions)")
            sys.exit(1)
        actions[idx]["status"] = "rejected"
        actions[idx]["reviewed"] = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
        save_suggestion(path, data)
        print(f"Rejected action {args.action_num} in {path.name}")
        return

    # ── Interactive review ──
    if args.review:
        path = _resolve(args.review, suggestion_files)
        if not path:
            sys.exit(1)
        data = load_suggestion(path)
        actions = data.get("actions", [])

        print(f"\n{'=' * 60}")
        print(f"Reviewing: {data.get('target', path.name)}")
        print(f"Rationale: {data.get('rationale', '')}")
        print(f"{'=' * 60}\n")

        for i, action in enumerate(actions, 1):
            if action.get("status", "pending") != "pending":
                describe_action(i, action)
                print(f"    (already {action.get('status')}, skipping)\n")
                continue

            describe_action(i, action)

            while True:
                choice = input(f"  Action {i}: [a]pprove / [r]eject / [s]kip / [q]uit? ").strip().lower()
                if choice in ("a", "approve"):
                    action["status"] = "approved"
                    action["reviewed"] = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
                    save_suggestion(path, data)
                    print(f"    → Approved\n")
                    break
                elif choice in ("r", "reject"):
                    action["status"] = "rejected"
                    action["reviewed"] = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
                    save_suggestion(path, data)
                    print(f"    → Rejected\n")
                    break
                elif choice in ("s", "skip"):
                    print(f"    → Skipped\n")
                    break
                elif choice in ("q", "quit"):
                    print("Review aborted.")
                    return
        return

    # ── Execute approved actions (or dry-run) ──
    any_approved = False
    for f in suggestion_files:
        data = load_suggestion(f)
        actions = data.get("actions", [])
        for i, action in enumerate(actions):
            if action.get("status") != "approved":
                continue
            any_approved = True

            print(f"\n{'=' * 60}")
            print(f"File: {f.name} — Action {i + 1}: {action.get('type')}")
            print(f"{'=' * 60}")
            describe_action(i + 1, action)

            ok = execute_action(action, dry_run=args.dry_run)

            if ok and not args.dry_run:
                action["status"] = "executed"
                action["executed"] = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
                save_suggestion(f, data)
                print(f"    → Executed\n")

    if not any_approved:
        print("No approved actions to execute.")
        print("Use --review <file> to approve individual actions first.")


if __name__ == "__main__":
    main()
