"""
Scan local Thunderbird mailboxes — metadata overview, incremental deltas, and deep body scans.

Three modes:
- Full scan (default): Metadata overview of all accounts/folders
- Incremental (--incremental): Only folders with new mails since last scan
- Deep (--deep --folder X): Read mail bodies, reconstruct threads, optionally filter with local LLM

Usage:
    uv run python scripts/scan-email.py                                    # full metadata scan
    uv run python scripts/scan-email.py --incremental                      # only new mails
    uv run python scripts/scan-email.py --deep --folder "INBOX/Work"       # read bodies
    uv run python scripts/scan-email.py --deep --folder "INBOX/Work" --model gemma4:e4b  # with LLM filter
    uv run python scripts/scan-email.py --follow-requests                  # process one request from raw/requests/
    uv run python scripts/scan-email.py --dry-run                          # show structure only
    uv run python scripts/scan-email.py --account work                     # one account only
"""

from __future__ import annotations

import argparse
import email.header
import email.utils
import json
import mailbox
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import EMAIL_STATE_FILE, RAW_DIR, RAW_REQUESTS_DIR, ROOT_DIR, today_iso

from wiki_config import CONFIG  # noqa: E402

_TB_PROFILE_RAW = CONFIG.personal.thunderbird_profile
THUNDERBIRD_PROFILE = (
    Path(_TB_PROFILE_RAW).expanduser() if _TB_PROFILE_RAW else Path()
)


def now_slug() -> str:
    """Timestamp slug for unique filenames: 2026-04-13T1842."""
    return datetime.now().strftime("%Y-%m-%dT%H%M")
REPORT_DIR = RAW_DIR / "notes" / "email"

import ollama_client  # noqa: E402


def _build_accounts() -> dict[str, dict]:
    """Materialise CONFIG.personal.accounts into runtime form.

    Resolves each account's relative `mbox_paths` against `thunderbird_profile`.
    Falls back to `email` for the display label when none is configured.
    """
    out: dict[str, dict] = {}
    for aid, info in CONFIG.personal.accounts.items():
        email_addr = info.get("email", "")
        out[aid] = {
            "email": email_addr,
            "label": info.get("label") or email_addr or aid,
            "paths": [THUNDERBIRD_PROFILE / p for p in info.get("mbox_paths", [])],
        }
    return out


ACCOUNTS = _build_accounts()


# ── Email State ──────────────────────────────────────────────────────

def load_email_state() -> dict:
    if EMAIL_STATE_FILE.exists():
        try:
            return json.loads(EMAIL_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"mboxes": {}, "last_incremental": None}


def save_email_state(state: dict) -> None:
    EMAIL_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── mbox discovery ───────────────────────────────────────────────────

def find_mbox_files(base_path: Path, folder_filter: str | None = None) -> list[tuple[str, Path]]:
    """Recursively find all mbox files under a base path.

    If folder_filter is set, only return mbox files whose folder name
    contains the filter string (case-insensitive, recursive).
    """
    results = []
    if not base_path.exists():
        return results

    for root, dirs, files in os.walk(base_path):
        for f in files:
            path = Path(root) / f
            if (f.endswith(".msf") or f.startswith("msgFilterRules.dat")
                    or f in ("filterlog.html", "popstate.dat", ".DS_Store")):
                continue
            if path.is_file() and path.stat().st_size > 1024:
                rel = path.relative_to(base_path)
                folder_name = str(rel).replace(".sbd/", " / ").replace(".sbd", "")

                if folder_filter:
                    if folder_filter.lower() not in folder_name.lower():
                        continue

                results.append((folder_name, path))

    return sorted(results, key=lambda x: x[0])


# ── Metadata scan (existing) ────────────────────────────────────────

def scan_mbox_metadata(path: Path, since: datetime | None = None) -> dict:
    """Scan a single mbox file — headers only.

    If since is set, only include messages with Date after that timestamp.
    """
    try:
        mbox = mailbox.mbox(str(path))
    except Exception as e:
        return {"error": str(e), "count": 0}

    count = 0
    years = Counter()
    senders = Counter()
    recipients = Counter()
    subjects = []
    date_range = [None, None]

    for key in mbox.keys():
        try:
            msg = mbox[key]
        except Exception:
            continue

        # Parse date first — skip if before cutoff
        dt = None
        date_str = msg.get("Date", "")
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            pass

        if since and dt:
            # Normalize both to aware or both to naive for comparison
            try:
                if dt.tzinfo is None:
                    dt_cmp = dt.replace(tzinfo=since.tzinfo)
                else:
                    dt_cmp = dt
                if dt_cmp < since:
                    continue
            except Exception:
                continue
        elif since and not dt:
            continue  # unknown date, skip in delta mode

        count += 1

        if dt:
            years[dt.year] += 1
            if date_range[0] is None or dt < date_range[0]:
                date_range[0] = dt
            if date_range[1] is None or dt > date_range[1]:
                date_range[1] = dt
        else:
            years["unknown"] += 1

        try:
            name, addr = email.utils.parseaddr(msg.get("From", ""))
            sender_label = name if name else addr
            if sender_label:
                try:
                    decoded = str(email.header.make_header(email.header.decode_header(sender_label)))
                    sender_label = decoded
                except Exception:
                    pass
                senders[sender_label] += 1
        except Exception:
            pass

        try:
            name, addr = email.utils.parseaddr(msg.get("To", ""))
            rec_label = name if name else addr
            if rec_label:
                recipients[rec_label] += 1
        except Exception:
            pass

        if count <= 5:
            try:
                subj = msg.get("Subject", "(no subject)")
                decoded = str(email.header.make_header(email.header.decode_header(subj)))
                subjects.append(decoded)
            except Exception:
                subjects.append("(decode error)")

    return {
        "count": count,
        "size_bytes": path.stat().st_size,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 1),
        "years": dict(sorted(years.items(), key=lambda x: (isinstance(x[0], str), x[0]))),
        "date_min": date_range[0].strftime("%Y-%m-%d") if date_range[0] else "?",
        "date_max": date_range[1].strftime("%Y-%m-%d") if date_range[1] else "?",
        "top_senders": dict(senders.most_common(10)),
        "top_recipients": dict(recipients.most_common(5)),
        "sample_subjects": subjects,
    }


# ── Deep scan (bodies) ───────────────────────────────────────────────

def extract_body(msg) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, errors="replace")
                except Exception:
                    pass
            elif ctype == "text/html" and not body:
                try:
                    import html2text
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    h = html2text.HTML2Text()
                    h.ignore_links = True
                    h.ignore_images = True
                    h.body_width = 0
                    body += h.handle(payload.decode(charset, errors="replace"))
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            pass
    return body.strip()


def reconstruct_threads(messages: list[dict]) -> list[dict]:
    """Group messages into threads by In-Reply-To / References headers."""
    by_id: dict[str, dict] = {}
    threads: list[list[dict]] = []

    for msg in messages:
        mid = msg.get("message_id", "")
        if mid:
            by_id[mid] = msg

    assigned = set()
    for msg in messages:
        if id(msg) in assigned:
            continue
        thread = [msg]
        assigned.add(id(msg))

        refs = msg.get("references", "").split() + [msg.get("in_reply_to", "")]
        for ref in refs:
            ref = ref.strip().strip("<>")
            if ref in by_id and id(by_id[ref]) not in assigned:
                thread.append(by_id[ref])
                assigned.add(id(by_id[ref]))

        threads.append(thread)

    result = []
    for thread in threads:
        thread.sort(key=lambda m: m.get("date_raw", ""))
        subject = thread[0].get("subject", "(no subject)")
        result.append({
            "subject": subject,
            "count": len(thread),
            "participants": list(set(m.get("from", "") for m in thread)),
            "date_range": f"{thread[0].get('date', '?')} — {thread[-1].get('date', '?')}",
            "messages": thread,
        })

    result.sort(key=lambda t: t["count"], reverse=True)
    return result


def scan_mbox_deep(path: Path, model: str | None = None, limit: int = 0) -> list[dict]:
    """Deep scan — read bodies, reconstruct threads, optionally filter with LLM."""
    try:
        mbox = mailbox.mbox(str(path))
    except Exception:
        return []

    messages = []
    for key in mbox.keys():
        try:
            msg = mbox[key]
        except Exception:
            continue

        date_str = msg.get("Date", "")
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            date_fmt = dt.strftime("%Y-%m-%d")
        except Exception:
            dt = None
            date_fmt = "?"

        try:
            from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
            from_label = from_name or from_addr
            subj = msg.get("Subject", "(no subject)")
            try:
                subj = str(email.header.make_header(email.header.decode_header(subj)))
            except Exception:
                pass
        except Exception:
            from_label = "?"
            subj = "?"

        body = extract_body(msg)
        if not body:
            continue

        messages.append({
            "subject": subj,
            "from": from_label,
            "date": date_fmt,
            "date_raw": date_str,
            "body": body[:2000],  # cap body to prevent massive threads
            "message_id": msg.get("Message-ID", "").strip("<>"),
            "in_reply_to": msg.get("In-Reply-To", "").strip("<>"),
            "references": msg.get("References", ""),
        })

    threads = reconstruct_threads(messages)

    if limit:
        threads = threads[:limit]

    # Optional LLM filtering
    if model and threads:
        threads = filter_threads_with_llm(threads, model)

    return threads


def filter_threads_with_llm(threads: list[dict], model: str) -> list[dict]:
    """Use local LLM to filter threads by relevance."""
    summaries = []
    for t in threads[:50]:  # cap to avoid huge prompts
        summaries.append(f"- \"{t['subject']}\" ({t['count']} msgs, {t['date_range']}, {', '.join(t['participants'][:3])})")

    prompt = f"""Review these email threads and classify each as RELEVANT or SKIP.

RELEVANT = contains decisions, insights, relationships, or knowledge worth preserving.
SKIP = automated notifications, receipts, newsletters, routine exchanges.

Threads:
{"\\n".join(summaries)}

Respond with ONLY a JSON array of booleans (true=relevant, false=skip), same order:"""

    try:
        raw = ollama_client.chat(prompt, model=model)
        verdicts = ollama_client.parse_json_lenient(raw)
        return [t for t, v in zip(threads, verdicts) if v]
    except Exception as e:
        print(f"  LLM filter failed ({e}), keeping all threads")
        return threads


# ── Report generation ────────────────────────────────────────────────

def generate_overview_report(all_data: dict) -> str:
    """Full metadata overview report."""
    lines = [
        "---", "type: email-scan", f"date: {today_iso()}",
        'origin: "thunderbird-local-scan"',
        "tags: [email, thunderbird, metadata, overview]",
        "language: de", "---", "",
        "# Thunderbird Email Overview", "",
        f"> Metadata-Scan vom {today_iso()}. Nur Headers gelesen, kein Body-Content.", "",
    ]

    total_mails = 0
    total_folders = 0

    for account_id, account_data in all_data.items():
        account_info = ACCOUNTS[account_id]
        lines.append(f"## {account_info['label']}")
        lines.append("")

        account_total = 0
        for folder_name, stats in account_data["folders"]:
            total_folders += 1
            count = stats.get("count", 0)
            account_total += count

            if stats.get("error"):
                lines.append(f"### {folder_name} — ERROR: {stats['error']}")
                lines.append("")
                continue

            lines.append(f"### {folder_name}")
            lines.append(f"- **{count} Mails** ({stats.get('size_mb', 0)} MB, {stats.get('date_min', '?')} — {stats.get('date_max', '?')})")

            top = stats.get("top_senders", {})
            if top:
                lines.append(f"- Top Sender: {', '.join(f'{n} ({c})' for n, c in list(top.items())[:5])}")

            subjects = stats.get("sample_subjects", [])
            if subjects:
                lines.append(f"- Beispiel-Betreffs: {', '.join(subjects[:3])}")

            lines.append("")

        total_mails += account_total
        lines.append(f"**Account gesamt: {account_total} Mails**")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.insert(4, f"> {total_mails} Mails in {total_folders} Ordnern gescannt.")
    lines.insert(5, "")
    return "\n".join(lines)


def generate_delta_report(changed_folders: dict) -> str:
    """Delta report — only changed folders since last scan."""
    lines = [
        "---", "type: email-delta", f"date: {today_iso()}",
        'origin: "thunderbird-incremental-scan"',
        "tags: [email, thunderbird, metadata, delta]",
        "language: de", "---", "",
        "# Email Delta", "",
        f"> Inkrementeller Scan vom {today_iso()}. Nur Ordner mit neuen Mails.", "",
    ]

    for folder_path, stats in changed_folders.items():
        account = stats.get("account", "unknown")
        account_email = stats.get("account_email", "")
        lines.append(f"## {folder_path}")
        lines.append(f"- **Account:** {account}" + (f" ({account_email})" if account_email else ""))
        lines.append(f"- **{stats['count']} neue Mails** ({stats.get('size_mb', 0)} MB)")
        lines.append(f"- Zeitraum: {stats.get('date_min', '?')} — {stats.get('date_max', '?')}")

        top = stats.get("top_senders", {})
        if top:
            lines.append(f"- Top Sender: {', '.join(f'{n} ({c})' for n, c in list(top.items())[:5])}")
        lines.append("")

    return "\n".join(lines)


def generate_deep_report(folder: str, threads: list[dict]) -> str:
    """Deep scan report — thread summaries with bodies."""
    lines = [
        "---", "type: email-deep-scan", f"date: {today_iso()}",
        f'origin: "thunderbird-deep-scan/{folder}"',
        "tags: [email, thunderbird, deep-scan, threads]",
        "language: de", "---", "",
        f"# Email Deep Scan: {folder}", "",
        f"> {len(threads)} Threads gescannt. Bodies gelesen und destilliert.", "",
    ]

    for t in threads:
        lines.append(f"## {t['subject']}")
        lines.append(f"- **{t['count']} Nachrichten** ({t['date_range']})")
        lines.append(f"- Teilnehmer: {', '.join(t['participants'][:5])}")
        lines.append("")

        for msg in t["messages"][:5]:  # max 5 messages per thread in report
            lines.append(f"### {msg['from']} ({msg['date']})")
            lines.append("")
            body_preview = msg["body"][:500]
            lines.append(body_preview)
            lines.append("")

        if t["count"] > 5:
            lines.append(f"*... +{t['count'] - 5} weitere Nachrichten*")
            lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scan Thunderbird mailboxes")
    parser.add_argument("--dry-run", action="store_true", help="Only show folder structure")
    parser.add_argument("--account", type=str, help="Only scan one account")
    parser.add_argument("--incremental", action="store_true", help="Only scan folders with new mails")
    parser.add_argument("--deep", action="store_true", help="Read mail bodies (not just headers)")
    parser.add_argument("--folder", type=str, help="Folder filter for --deep (e.g. 'INBOX/Work')")
    parser.add_argument("--model", type=str, help="Local LLM model for --deep filtering (e.g. gemma4:e4b)")
    parser.add_argument("--limit", type=int, default=0, help="Max threads for --deep")
    parser.add_argument("--follow-requests", action="store_true", help="Process one request from raw/requests/")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Follow requests mode ──
    if args.follow_requests:
        RAW_REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        request_files = sorted(RAW_REQUESTS_DIR.glob("*.json"))
        pending = [f for f in request_files if json.loads(f.read_text()).get("status") == "pending"
                    and json.loads(f.read_text()).get("type") == "email-deep-scan"]
        if not pending:
            print("No pending email deep-scan requests.")
            return

        req_file = pending[0]
        req = json.loads(req_file.read_text())
        print(f"Processing request: {req_file.name}")
        print(f"  Folder: {req.get('folder')}")
        print(f"  Rationale: {req.get('rationale', '')}")

        # Update status
        req["status"] = "processing"
        req_file.write_text(json.dumps(req, indent=2))

        # Run deep scan
        args.deep = True
        args.folder = req.get("folder")
        args.model = req.get("model")
        # Fall through to deep scan below

    # ── Deep scan mode ──
    if args.deep:
        if not args.folder:
            print("--deep requires --folder")
            return

        print(f"Deep scan: {args.folder}")
        all_threads = []

        accounts_to_scan = ACCOUNTS
        if args.account:
            accounts_to_scan = {args.account: ACCOUNTS[args.account]}

        for account_id, account_info in accounts_to_scan.items():
            for base_path in account_info["paths"]:
                mbox_files = find_mbox_files(base_path, folder_filter=args.folder)
                for folder_name, path in mbox_files:
                    print(f"  Reading bodies: {folder_name}...", end=" ", flush=True)
                    threads = scan_mbox_deep(path, model=args.model, limit=args.limit)
                    print(f"{len(threads)} threads")
                    all_threads.extend(threads)

        if not all_threads:
            print("No threads found.")
            return

        folder_slug = args.folder.lower().replace("/", "-").replace(" ", "-")
        report = generate_deep_report(args.folder, all_threads)
        report_path = REPORT_DIR / f"deep-{folder_slug}-{now_slug()}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\nDeep scan report: {report_path.relative_to(ROOT_DIR)}")
        print(f"{len(all_threads)} threads saved.")

        # Mark request as done if we came from --follow-requests
        if args.follow_requests:
            req["status"] = "done"
            req_file.write_text(json.dumps(req, indent=2))
            print(f"Request marked as done: {req_file.name}")

        return

    # ── Incremental mode ──
    if args.incremental:
        state = load_email_state()
        changed_folders = {}

        accounts_to_scan = ACCOUNTS
        if args.account:
            accounts_to_scan = {args.account: ACCOUNTS[args.account]}

        for account_id, account_info in accounts_to_scan.items():
            for base_path in account_info["paths"]:
                mbox_files = find_mbox_files(base_path)
                for folder_name, path in mbox_files:
                    rel_key = str(path.relative_to(THUNDERBIRD_PROFILE))
                    current_size = path.stat().st_size
                    prev = state["mboxes"].get(rel_key, {})
                    prev_size = prev.get("size", 0)

                    if current_size == prev_size:
                        continue  # unchanged

                    # First run for this folder: just record baseline, don't scan
                    if not prev:
                        print(f"  New: {folder_name} (baseline recorded, will scan on next run)")
                        state["mboxes"][rel_key] = {
                            "size": current_size,
                            "count": 0,
                            "last_scan": today_iso(),
                        }
                        continue

                    delta_bytes = current_size - prev_size
                    last_scan_str = prev.get("last_scan", "")
                    since = None
                    if last_scan_str:
                        try:
                            from zoneinfo import ZoneInfo
                            since = datetime.fromisoformat(last_scan_str + "T00:00:00").replace(
                                tzinfo=ZoneInfo(CONFIG.scheduling.timezone)
                            )
                        except Exception:
                            pass
                    print(f"  Changed: [{account_id}] {folder_name} ({'+' if delta_bytes >= 0 else ''}{delta_bytes} bytes, since={last_scan_str or 'never'})")
                    stats = scan_mbox_metadata(path, since=since)
                    stats["account"] = account_id
                    stats["account_email"] = account_info.get("email", account_id)
                    report_key = f"[{account_id}] {folder_name}"
                    changed_folders[report_key] = stats

                    state["mboxes"][rel_key] = {
                        "size": current_size,
                        "count": stats.get("count", 0),
                        "last_scan": today_iso(),
                    }

        if not changed_folders:
            print("No changes since last scan.")
            save_email_state(state)
            return

        state["last_incremental"] = today_iso()
        save_email_state(state)

        report = generate_delta_report(changed_folders)
        report_path = REPORT_DIR / f"delta-{now_slug()}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\nDelta report: {report_path.relative_to(ROOT_DIR)}")
        print(f"{len(changed_folders)} folders changed.")
        return

    # ── Full scan mode (default) ──
    accounts_to_scan = ACCOUNTS
    if args.account:
        if args.account not in ACCOUNTS:
            print(f"Unknown account: {args.account}")
            print(f"Available: {', '.join(ACCOUNTS.keys())}")
            return
        accounts_to_scan = {args.account: ACCOUNTS[args.account]}

    state = load_email_state()
    all_data = {}

    for account_id, account_info in accounts_to_scan.items():
        print(f"\n{'='*60}")
        print(f"Account: {account_info['label']}")
        print(f"{'='*60}")

        folders = []
        for base_path in account_info["paths"]:
            mbox_files = find_mbox_files(base_path)
            print(f"  Found {len(mbox_files)} folders in {base_path.name}")

            for folder_name, path in mbox_files:
                if args.dry_run:
                    size_mb = path.stat().st_size / 1024 / 1024
                    print(f"    {folder_name}: {size_mb:.1f} MB")
                    folders.append((folder_name, {"count": 0, "size_mb": round(size_mb, 1)}))
                else:
                    print(f"    Scanning: {folder_name}...", end=" ", flush=True)
                    stats = scan_mbox_metadata(path)
                    print(f"{stats['count']} mails")
                    folders.append((folder_name, stats))

                    # Update state
                    rel_key = str(path.relative_to(THUNDERBIRD_PROFILE))
                    state["mboxes"][rel_key] = {
                        "size": stats.get("size_bytes", path.stat().st_size),
                        "count": stats.get("count", 0),
                        "last_scan": today_iso(),
                    }

        all_data[account_id] = {"folders": folders}

    if args.dry_run:
        print("\n[dry-run] No report generated.")
        return

    save_email_state(state)

    report = generate_overview_report(all_data)
    report_path = REPORT_DIR / f"thunderbird-overview-{now_slug()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path.relative_to(ROOT_DIR)}")
    print("Run 'uv run python scripts/compile.py' to compile into wiki articles.")


if __name__ == "__main__":
    main()
