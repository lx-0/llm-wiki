"""Wispr Flow meetings via the desktop application's direct HTTP API.

Verified against the installed app and live service on 2026-10-09. The sync
request always sends an empty meetings list: pull only, never upload/delete.
No MCP or local meeting database. App session files are read for auth only;
Wispr owns token renewal. Missing/expired credentials fail with a login hint.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from collectors.base import (
    CollectorSpec, RunResult, filter_accounts, register, resolve_accounts, run_account_loop,
)
from core import daily_capture, frontmatter
from core.config import CONFIG, TIMEZONE
from core.paths import ROOT_DIR, STATE_DIR
from core.state_store import locked
from core.utils import load_json_state, now_iso, save_json_state, slugify

log = logging.getLogger(__name__)
_BASE_URL = "https://api.wisprflow.ai"
_STATE_FILE = STATE_DIR / "wispr-state.json"
_OUTPUT = "raw/transcripts/wispr"


class WisprAPIError(RuntimeError):
    """Transport, auth or schema error; never includes credentials/response bodies."""


@dataclass(frozen=True)
class WisprAccount:
    account_id: str
    access_token_env: str
    session_file: str
    user_id: str

    def token(self) -> str:
        if self.access_token_env:
            value = os.environ.get(self.access_token_env, "").strip()
            if value:
                return value
            raise WisprAPIError(f"set {self.access_token_env} to a current Wispr access token")
        if not self.session_file or not self.user_id:
            raise WisprAPIError("configure session_file and user_id, or access_token_env")
        try:
            data = json.loads(Path(self.session_file).expanduser().read_text())
            session = data["workosSession"]
            if session["userId"] != self.user_id:
                raise WisprAPIError("Wispr app is signed into a different configured user")
            token = session["accessToken"]
            if not isinstance(token, str) or not token:
                raise ValueError("empty token")
            return token
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WisprAPIError("cannot read Wispr session; open Wispr Flow and sign in") from exc


def _accounts() -> list[WisprAccount]:
    return resolve_accounts(
        CONFIG.personal.accounts, "wispr-api",
        lambda name, block: WisprAccount(
            name, str(block.get("access_token_env") or ""),
            str(block.get("session_file") or ""), str(block.get("user_id") or ""),
        ), block_key="wispr",
    )


class WisprClient:
    def __init__(self, account: WisprAccount, *, transport=None):
        self.account = account
        self.http = httpx.Client(
            base_url=_BASE_URL, timeout=float(CONFIG.limits.wispr_request_timeout_s),
            transport=transport, follow_redirects=False,
        )

    def close(self) -> None:
        self.http.close()

    def page(self, since: str, cursor: str | None) -> dict:
        body = {
            "meetings": [], "last_sync_time": since, "hard_refresh": since == "0",
            # Ask for inline full transcripts, not only a changed-artifact stamp.
            "supports_refined_stamp_fetch": False,
        }
        if cursor is not None:
            body["cursor"] = cursor
        for attempt in range(2):
            try:
                response = self.http.post(
                    "/api/v1/meetings/sync", json=body,
                    # Wispr's desktop API uses the raw token, without Bearer.
                    headers={"Authorization": self.account.token()},
                )
            except httpx.HTTPError as exc:
                if not attempt:
                    continue
                raise WisprAPIError("Wispr network request failed") from exc
            if response.status_code in (401, 403):
                raise WisprAPIError(
                    f"Wispr HTTP {response.status_code}: open Flow and sign in; "
                    "check cloud-sync access or renew the configured token"
                )
            if response.status_code == 429 or response.status_code >= 500:
                if not attempt:
                    try:
                        delay = min(float(response.headers.get("Retry-After", "1")), 30)
                    except ValueError:
                        delay = 1
                    time.sleep(max(0, delay))
                    continue
            if response.status_code != 200:
                raise WisprAPIError(f"Wispr sync HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise WisprAPIError("Wispr sync returned invalid JSON") from exc
            if not isinstance(data, dict) or not isinstance(data.get("pull"), list):
                raise WisprAPIError("Wispr sync response is missing its pull list")
            if not isinstance(data.get("sync_time"), str) or not data["sync_time"].isdigit():
                raise WisprAPIError("Wispr sync response has an invalid sync_time")
            if data.get("next_cursor") is not None and not isinstance(data["next_cursor"], str):
                raise WisprAPIError("Wispr sync response has an invalid cursor")
            if data.get("acked") or data.get("rejected"):
                raise WisprAPIError("unexpected acknowledgements for a pull-only sync")
            return data
        raise WisprAPIError("Wispr sync exhausted retries")


def _date(value: object) -> datetime:
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        # Desktop sync uses timezone-less UTC; verified against the same
        # meeting's Z-suffixed MCP timestamp and the desktop date converter.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _text(value: object) -> str:
    """Plain text/Markdown, or Lexical JSON used by the desktop notes editor.

    Preserve unknown structured content verbatim rather than silently dropping
    source information. Refined NDJSON transcripts remain lossless code blocks.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise WisprAPIError("unexpected non-string meeting content")
    value = value.strip()
    if not value:
        return ""
    try:
        doc = json.loads(value)
    except ValueError:
        return value
    if isinstance(doc, dict) and isinstance(doc.get("root"), dict):
        def walk(node: dict) -> str:
            kind = node.get("type")
            if kind == "text":
                return str(node.get("text", ""))
            if kind == "linebreak":
                return "\n"
            children = node.get("children", [])
            text = "".join(walk(child) for child in children)
            if kind in ("paragraph", "heading", "listitem", "quote"):
                return text + "\n"
            if kind in ("root", "list", "link", "autolink"):
                return text
            raise WisprAPIError(f"unsupported Wispr note node: {kind!r}")
        try:
            return walk(doc["root"]).strip()
        except (WisprAPIError, TypeError, AttributeError):
            log.warning("Preserving unsupported Wispr note JSON verbatim")
    return "```json\n" + value + "\n```"


def _render(row: dict, account_id: str) -> tuple[dict, str, str, bool]:
    mid = str(UUID(row["id"]))
    started = _date(row["created_at"])
    date = started.astimezone(ZoneInfo(TIMEZONE)).date().isoformat()
    summary, notes = _text(row.get("summary")), _text(row.get("notes"))
    deleted = bool(row.get("transcript_deleted_at"))
    transcript = "" if deleted else _text(row.get("refined_transcript"))
    sections = [("Summary", summary), ("Notes", notes), ("Transcript", transcript)]
    title = str(row.get("title") or mid).replace("\n", " ")
    body = f"# {title}\n\n" + "\n\n".join(
        f"## {heading}\n\n{text}" for heading, text in sections if text
    ) + "\n"
    fm = {
        "type": "transcript", "source": "wispr", "meeting_id": mid,
        "account_id": account_id, "title": title, "started_at": started.isoformat(),
        "modified_at": row.get("modified_at"), "tags": ["wispr", "meeting"],
        "participants": row.get("contacts") or [],
        "transcript_status": "deleted" if deleted else "available" if transcript else "pending",
    }
    if row.get("ended_at"):
        fm["ended_at"] = _date(row["ended_at"]).isoformat()
    if row.get("calendar_external_id"):
        fm["calendar_event"] = row["calendar_external_id"]
    return fm, body, date, any(text for _, text in sections)


@register
class WisprCollector:
    SPEC = CollectorSpec(
        name="wispr", output_subfolder=_OUTPUT, piggyback_default=True,
        piggyback_cooldown_hours=6, supports_incremental=True, supports_account_loop=True,
    )

    def is_configured(self) -> bool:
        return any(
            (a.access_token_env and os.environ.get(a.access_token_env))
            or (a.session_file and a.user_id and Path(a.session_file).expanduser().is_file())
            for a in _accounts()
        )

    def run(self, *, dry_run=False, incremental=False, account=None) -> RunResult:
        accounts = filter_accounts(_accounts(), account)
        if not accounts:
            return RunResult(message="no Wispr accounts configured",
                             errors=(f"unknown account: {account}",) if account else ())
        # Serialize source updates + watermark changes, also against manual runs.
        context = nullcontext() if dry_run else locked(_STATE_FILE.with_suffix(".lock"))
        with context:
            state = load_json_state(_STATE_FILE)
            outcome = run_account_loop(
                accounts, lambda a: self._scan(a, state, dry_run, incremental),
                log=log, name="wispr",
            )
            if not dry_run and outcome.any_state_touched:
                save_json_state(_STATE_FILE, state)
        return RunResult(
            files_written=tuple(p for files, _ in outcome.payloads for p in files),
            files_skipped=sum(n for _, n in outcome.payloads),
            state_keys_touched=("wispr-state.json",) if outcome.any_state_touched else (),
            message="; ".join(outcome.messages), errors=tuple(outcome.error_ids),
        )

    def _scan(self, account: WisprAccount, state: dict, dry_run: bool, incremental: bool):
        saved = state.get(account.account_id, {})
        items = dict(saved.get("items", {}))
        since = saved.get("sync_time", "0") if incremental else "0"
        client = WisprClient(account)
        written, skipped, pending = [], 0, 0
        cursor, seen_cursors, changed = None, set(), 0
        complete = False
        sync_time = since
        try:
            for page_number in range(CONFIG.limits.wispr_max_pages):
                page = client.page(since, cursor)
                if page_number == 0:
                    # Anchor to the first response. Later pages must not move
                    # past updates made while this scan was in flight.
                    sync_time = page["sync_time"]
                if int(sync_time) < int(since):
                    raise WisprAPIError("Wispr sync_time moved backwards")
                for row in page["pull"]:
                    if not isinstance(row, dict):
                        raise WisprAPIError("invalid Wispr meeting row")
                    if row.get("is_deleted") or row.get("is_tour_demo"):
                        skipped += 1
                        continue
                    if row.get("is_recording") or not row.get("finalized"):
                        pending += 1
                        continue
                    fm, body, date, has_content = _render(row, account.account_id)
                    if not has_content:
                        pending += 1
                        continue
                    if fm["transcript_status"] == "pending":
                        pending += 1  # re-pull until the transcript is ready
                    mid = fm["meeting_id"]
                    digest = hashlib.sha256(frontmatter.serialize(fm, body).encode()).hexdigest()
                    previous = items.get(mid, {})
                    # Full UUID, stable path across title edits, no account-id path interpolation.
                    name = previous.get("filename") or f"{date}--{slugify(fm['title'])[:60]}--{mid}.md"
                    if Path(name).name != name or not name.endswith(f"--{mid}.md"):
                        raise WisprAPIError("invalid cached Wispr output filename")
                    target = ROOT_DIR / _OUTPUT / name
                    if previous.get("hash") == digest and target.exists():
                        skipped += 1
                        continue
                    if changed >= CONFIG.limits.wispr_max_per_run:
                        pending += 1
                        continue
                    changed += 1
                    if dry_run:
                        log.info("DRY: would write %s", target.relative_to(ROOT_DIR))
                        continue
                    fm["ingested_at"] = now_iso()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_suffix(".tmp")
                    frontmatter.write(temp, fm, body)
                    temp.replace(target)
                    # Only new meetings add a rollup line. Updates retain source provenance.
                    if not previous.get("rollup"):
                        daily_capture.append_with_source(
                            date, "meetings", f"- **wispr** · {fm['title']}",
                            target.relative_to(ROOT_DIR).as_posix(),
                        )
                    items[mid] = {"hash": digest, "filename": name, "rollup": True}
                    written.append(target)
                cursor = page.get("next_cursor")
                if cursor is None:
                    complete = True
                    break
                if not cursor or cursor in seen_cursors:
                    raise WisprAPIError("Wispr pagination cursor did not advance")
                seen_cursors.add(cursor)
            if not complete:
                raise WisprAPIError("Wispr pagination limit reached; watermark unchanged")
        finally:
            client.close()
            # Keep successful item dedup even when a later page fails. Never
            # advance the watermark on failure, pending work, or a bounded run.
            if not dry_run and written:
                state[account.account_id] = {"items": items, "sync_time": saved.get("sync_time", "0")}
                save_json_state(_STATE_FILE, state)
        if not dry_run:
            state[account.account_id] = {
                "items": items,
                "sync_time": sync_time if complete and not pending else saved.get("sync_time", "0"),
            }
        return (f"{len(written)} written, {skipped} unchanged, {pending} pending"
                + (f", {changed} would write" if dry_run else ""),
                (written, skipped), not dry_run)
