"""M033-S04-T05 — characterisation of `GmeetCollector._run_one_account`, the per-account
scan loop, with a fake Drive client and an isolated vault.

Pins what the operator's run, the state file and the logs can observe — messages,
filenames, frontmatter shape, the daily rollup line, watermark + dead-letter state — so the
split of the loop into its phases is provably a pure move. Before this file the loop had no
test at all; the other `test_gmeet_*` files cover the pure helpers.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from collectors import gmeet
from core import daily_capture

NOW = "2026-05-16T08:00:00+02:00"

NOTES = {
    "id": "doc-notes-0001",
    "name": "Sprint Sync – Notizen von Gemini",
    "createdTime": "2026-05-15T10:05:00Z",
    "webViewLink": "https://docs.google.com/document/d/doc-notes-0001/edit",
}
TRANSCRIPT = {
    "id": "doc-tx-0001",
    "name": "Sprint Sync – Transcript",
    "createdTime": "2026-05-15T10:09:00Z",
    "webViewLink": "https://docs.google.com/document/d/doc-tx-0001/edit",
}
NOTES_REGEN = {
    "id": "doc-notes-0002",
    "name": "Sprint Sync – Notizen von Gemini",
    "createdTime": "2026-05-15T10:07:00Z",
    "webViewLink": None,
}
EMAIL_DOC = {
    "id": "doc-mail-0001",
    "name": "Colleague Sync – Transcript",
    "createdTime": "2026-05-20T09:00:00Z",
    "webViewLink": None,
}
KEY = gmeet._meeting_key(NOTES["name"])
MEETING_FILE = f"2026-05-15--sprint-sync--{KEY}.md"


class _FakeDrive:
    """Stand-in for `_DriveClient`: a canned folder + docs, every call recorded."""

    def __init__(self, docs, *, folder_id="folder-1", fail_export=(), fail_list=False):
        self.docs = list(docs)
        self.folder_id = folder_id
        self.fail_export = set(fail_export)
        self.fail_list = fail_list
        self.calls: list[tuple] = []

    def resolve_folder_id(self, name):
        self.calls.append(("resolve_folder_id", name))
        return self.folder_id

    def list_docs(self, folder_id, *, since=None, limit=None):
        self.calls.append(("list_docs", folder_id, since, limit))
        if self.fail_list:
            raise gmeet.GmeetAPIError("403 on GET files: forbidden")
        yield from self.docs

    def export_doc(self, file_id):
        self.calls.append(("export_doc", file_id))
        if file_id in self.fail_export:
            raise gmeet.GmeetAPIError(f"unexpected 404 on GET {file_id}")
        return f"Exported body of {file_id}.\n"


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """An isolated vault: the collector's paths, the daily rollup dir, the clock, the
    OAuth session — everything but the Drive client, which each test installs."""
    monkeypatch.setattr(gmeet, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(gmeet, "_STATE_FILE", tmp_path / "state" / "gmeet-state.json")
    monkeypatch.setattr(daily_capture, "DAILY_DIR", tmp_path / "daily")
    monkeypatch.setattr(gmeet, "now_iso", lambda: NOW)
    monkeypatch.setattr(gmeet.google_oauth, "session", lambda app, aid: ("session", None))
    return tmp_path


def _collector(monkeypatch, fake: _FakeDrive, *, folder_id="folder-1", since=None):
    """One `gmeet-api` account (email discovery off) over the fake Drive client."""
    from core.config import CONFIG

    block = {
        "kind": "gmeet-api",
        "drive_folder_id": folder_id,
        "email_discovery": {"enabled": False},
    }
    if since:
        block["since"] = since
    monkeypatch.setattr(
        CONFIG.personal, "accounts", {"work": {"email": "alex@example.com", "gmeet": block}}
    )
    monkeypatch.setattr(gmeet, "_DriveClient", lambda session, timeout_s: fake)
    return gmeet.GmeetCollector()


def _run_scan(
    collector,
    *,
    state=None,
    already_present=None,
    sibling_map=None,
    dry_run=False,
    incremental=False,
):
    """Call the per-account scan the way `run()` does; returns (result, state, already, smap)."""
    state = {} if state is None else state
    already = set() if already_present is None else already_present
    smap = {} if sibling_map is None else sibling_map
    result = collector._run_one_account(
        collector._accounts[0],
        state=state,
        already_present=already,
        sibling_map=smap,
        dry_run=dry_run,
        incremental=incremental,
    )
    return result, state, already, smap


def _write_legacy_notes_file(root: Path) -> Path:
    """A pre-pairing-shape meeting file (singular `doc_kind` / `drive_doc_id`)."""
    out = root / "raw" / "transcripts" / "gmeet"
    out.mkdir(parents=True, exist_ok=True)
    p = out / "2026-05-13--sprint-sync--docnotes0001.md"
    p.write_text(
        "---\n"
        "type: transcript\n"
        "source: gmeet\n"
        "meeting_id: docnotes0001\n"
        "title: 'Sprint Sync'\n"
        "doc_kind: notes\n"
        "drive_doc_id: doc-notes-0001\n"
        "drive_doc_name: 'Sprint Sync – Notizen von Gemini'\n"
        "---\n\n"
        "## Summary\n\n"
        "Legacy body.\n",
        encoding="utf-8",
    )
    return p


def _frontmatter(text: str) -> str:
    return text.split("---\n", 2)[1]


# ── the write path ───────────────────────────────────────────────────


def test_fresh_pair_writes_one_meeting_file_and_the_rollup_line(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES, TRANSCRIPT])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, already, smap = _run_scan(collector)

    target = vault / "raw" / "transcripts" / "gmeet" / MEETING_FILE
    assert msg == "listed 2 · wrote 1 · skipped 0"
    assert files == [target] and skipped == 0 and touched is True
    text = target.read_text(encoding="utf-8")
    front = _frontmatter(text)
    assert "doc_kinds:\n- notes\n- transcript" in front
    assert f"meeting_id: {KEY}" in front
    assert "input_source: cli" in front and "account_id: work" in front
    assert text.index("## Summary") < text.index("## Transcript")
    assert "Exported body of doc-notes-0001." in text
    assert "Exported body of doc-tx-0001." in text
    # Folder docs advance the watermark; nothing failed, so no dead-letter key.
    assert state == {"work": {"last_seen_ts": "2026-05-15T10:09:00Z"}}
    rollup = (vault / "daily" / "2026-05-15" / "meetings.md").read_text(encoding="utf-8")
    assert f"- **gmeet** · Sprint Sync → [[{target.stem}]]" in rollup
    # The fresh file is registered for the rest of the run.
    assert smap[KEY].path == target and smap[KEY].doc_kinds == {"notes", "transcript"}
    assert already == {KEY, "docnotes0001", "doctx0001"}
    assert fake.calls == [
        ("list_docs", "folder-1", None, collector._accounts[0].max_per_run),
        ("export_doc", "doc-notes-0001"),
        ("export_doc", "doc-tx-0001"),
    ]


def test_export_failure_lands_in_the_dead_letter_and_the_rest_still_writes(
    monkeypatch, vault, caplog
) -> None:
    caplog.set_level(logging.WARNING, logger="collectors.gmeet")
    fake = _FakeDrive([NOTES, TRANSCRIPT], fail_export={"doc-notes-0001"})
    collector = _collector(monkeypatch, fake)

    (msg, (files, _skipped), touched), state, _already, _smap = _run_scan(collector)

    target = vault / "raw" / "transcripts" / "gmeet" / MEETING_FILE
    assert msg == "listed 2 · wrote 1 · skipped 0"
    assert files == [target] and touched is True
    assert "doc_kinds:\n- transcript\n" in _frontmatter(target.read_text(encoding="utf-8"))
    assert state == {
        "work": {
            "last_seen_ts": "2026-05-15T10:09:00Z",
            "export_failed": {
                "doc-notes-0001": {
                    "first_seen": NOW,
                    "attempts": 1,
                    "last_error": "unexpected 404 on GET doc-notes-0001",
                    "last_attempt": NOW,
                }
            },
        }
    }
    assert (
        "GmeetCollector[work]: export doc-notes-0001 — unexpected 404 on GET doc-notes-0001"
        in caplog.text
    )


def test_parked_dead_letter_id_is_not_exported(monkeypatch, vault, caplog) -> None:
    from core.config import CONFIG

    caplog.set_level(logging.INFO, logger="collectors.gmeet")
    budget = CONFIG.limits.gmeet_export_dead_letter_attempts
    reprobe = CONFIG.limits.gmeet_export_dead_letter_reprobe_days
    parked = {"first_seen": NOW, "attempts": budget, "last_error": "404", "last_attempt": NOW}
    state = {"work": {"export_failed": {"doc-notes-0001": dict(parked)}}}
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, _already, _smap = _run_scan(collector, state=state)

    assert msg == "listed 1 · wrote 0 · skipped 0 · 1 dead-letter"
    assert files == [] and skipped == 0 and touched is False
    assert state == {"work": {"export_failed": {"doc-notes-0001": parked}}}
    assert ("export_doc", "doc-notes-0001") not in fake.calls
    assert (
        f"GmeetCollector[work]: 1 un-exportable doc(s) parked in dead-letter (re-probe after {reprobe}d)"
        in caplog.text
    )


def test_dry_run_writes_nothing_and_touches_no_state(monkeypatch, vault, caplog) -> None:
    caplog.set_level(logging.INFO, logger="collectors.gmeet")
    fake = _FakeDrive([NOTES, TRANSCRIPT])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, already, smap = _run_scan(collector, dry_run=True)

    assert msg == "listed 2 · wrote 0 · skipped 0"
    assert files == [] and skipped == 0 and touched is False
    assert state == {} and already == set() and smap == {}
    assert not (vault / "raw").exists() and not (vault / "daily").exists()
    assert (
        f"  DRY[work]: would write raw/transcripts/gmeet/{MEETING_FILE} (2 Doc(s), " in caplog.text
    )


def test_incremental_scan_lists_since_the_watermark(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake)
    state = {"work": {"last_seen_ts": "2026-05-01T00:00:00Z"}}

    (msg, (files, _skipped), touched), state, _already, _smap = _run_scan(
        collector, state=state, incremental=True
    )

    assert msg == "listed 1 · wrote 1 · skipped 0" and touched is True
    assert fake.calls[0] == ("list_docs", "folder-1", "2026-05-01T00:00:00Z", 50)
    assert state == {"work": {"last_seen_ts": "2026-05-15T10:05:00Z"}}
    assert "input_source: piggyback" in _frontmatter(files[0].read_text(encoding="utf-8"))


def test_full_scan_lists_since_the_configured_date(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake, since="2026-01-01T00:00:00Z")

    _run_scan(collector, state={"work": {"last_seen_ts": "2026-05-01T00:00:00Z"}})

    assert fake.calls[0] == ("list_docs", "folder-1", "2026-01-01T00:00:00Z", 50)


# ── the merge path ───────────────────────────────────────────────────


def test_new_transcript_merges_into_the_legacy_sibling(monkeypatch, vault, caplog) -> None:
    caplog.set_level(logging.INFO, logger="collectors.gmeet")
    legacy = _write_legacy_notes_file(vault)
    smap, already = gmeet._scan_siblings(legacy.parent)
    fake = _FakeDrive([TRANSCRIPT])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, already, smap = _run_scan(
        collector, already_present=already, sibling_map=smap
    )

    assert msg == "listed 1 · wrote 1 · skipped 0"
    assert files == [legacy] and skipped == 0 and touched is True
    assert [p.name for p in legacy.parent.iterdir()] == [legacy.name]
    text = legacy.read_text(encoding="utf-8")
    front = _frontmatter(text)
    assert "doc_kinds:\n- notes\n- transcript" in front
    assert "id: doc-notes-0001" in front and "id: doc-tx-0001" in front
    assert "doc_kind:" not in front and "drive_doc_id:" not in front
    assert "Legacy body." in text
    assert text.index("## Summary") < text.index("## Transcript")
    assert state == {"work": {"last_seen_ts": "2026-05-15T10:09:00Z"}}
    assert smap[KEY].path == legacy and smap[KEY].doc_kinds == {"notes", "transcript"}
    assert "doctx0001" in already
    assert "  [work] merged 1 Doc(s) into raw/transcripts/gmeet/" + legacy.name in caplog.text
    assert not (vault / "daily").exists()  # the rollup line is written on fresh files only


def test_same_kind_already_present_in_the_sibling_is_skipped(monkeypatch, vault) -> None:
    legacy = _write_legacy_notes_file(vault)
    smap, already = gmeet._scan_siblings(legacy.parent)
    fake = _FakeDrive([NOTES_REGEN])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, _already, _smap = _run_scan(
        collector, already_present=already, sibling_map=smap
    )

    assert msg == "listed 1 · wrote 0 · skipped 1"
    assert files == [] and skipped == 1 and touched is False and state == {}
    assert ("export_doc", "doc-notes-0002") not in fake.calls


def test_known_short_id_is_skipped_without_export(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake)

    (msg, (files, skipped), touched), state, _already, _smap = _run_scan(
        collector, already_present={"docnotes0001"}
    )

    assert msg == "listed 1 · wrote 0 · skipped 1"
    assert files == [] and skipped == 1 and touched is False and state == {}
    assert fake.calls == [("list_docs", "folder-1", None, 50)]


# ── discovery edges ──────────────────────────────────────────────────


def test_auth_failure_returns_before_any_drive_call(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake)
    monkeypatch.setattr(gmeet.google_oauth, "session", lambda app, aid: (None, "token missing"))

    result, state, _already, _smap = _run_scan(collector)

    assert result == ("auth: token missing", ([], 0), False)
    assert fake.calls == [] and state == {}


def test_folder_list_failure_is_a_noop_with_a_note(monkeypatch, vault) -> None:
    fake = _FakeDrive([], fail_list=True)
    collector = _collector(monkeypatch, fake)

    result, _state, _already, _smap = _run_scan(collector)

    assert result == ("no-op · folder-list failed: 403 on GET files: forbidden", ([], 0), False)


def test_missing_folder_names_the_config_key(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES], folder_id=None)
    collector = _collector(monkeypatch, fake, folder_id="")

    result, _state, _already, _smap = _run_scan(collector)

    assert result == (
        "no-op · folder 'Meet Recordings' not found "
        "(set personal.accounts.work.gmeet.drive_folder_id)",
        ([], 0),
        False,
    )
    assert fake.calls == [("resolve_folder_id", "Meet Recordings")]


def test_auto_resolved_folder_warns_to_pin_it(monkeypatch, vault, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="collectors.gmeet")
    fake = _FakeDrive([NOTES], folder_id="folder-9")
    collector = _collector(monkeypatch, fake, folder_id="")

    (msg, _payload, _touched), _state, _already, _smap = _run_scan(collector)

    assert msg == "listed 1 · wrote 1 · skipped 0"
    assert fake.calls[:2] == [
        ("resolve_folder_id", "Meet Recordings"),
        ("list_docs", "folder-9", None, 50),
    ]
    assert (
        "GmeetCollector[work]: drive_folder_id is empty — auto-resolved by name to folder-9. "
        "Pin it in config (personal.accounts.work.gmeet.drive_folder_id) for collision-safe runs."
        in caplog.text
    )


def test_email_discovered_doc_is_ingested_without_moving_the_watermark(monkeypatch, vault) -> None:
    fake = _FakeDrive([NOTES])
    collector = _collector(monkeypatch, fake)
    monkeypatch.setattr(
        gmeet.GmeetCollector,
        "_discover_via_email",
        lambda self, acct, client, already: ([NOTES, EMAIL_DOC], "email: 2 linked / 2 new"),
    )

    (msg, (files, skipped), touched), state, _already, _smap = _run_scan(collector)

    # The folder doc seen by both sources ingests once; the colleague's doc is a second
    # meeting; only the own-folder doc moves `last_seen_ts`.
    assert msg == "email: 2 linked / 2 new · wrote 2 · skipped 0"
    assert [f.name for f in files] == [
        MEETING_FILE,
        f"2026-05-20--colleague-sync--{gmeet._meeting_key(EMAIL_DOC['name'])}.md",
    ]
    assert skipped == 0 and touched is True
    assert state == {"work": {"last_seen_ts": "2026-05-15T10:05:00Z"}}
