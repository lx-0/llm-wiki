"""S02 — adapter resolution + Thunderbird .dat round-trip + ConfigError on legacy schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.mailbox import MailboxFilter, MailboxReader, resolve_filter, resolve_reader
from adapters.mailbox.thunderbird import (
    ThunderbirdMboxReader,
    ThunderbirdMsgFilter,
    _from_dat_rule,
    _to_dat_rule,
)
from domain.mail import FilterAction, FilterCondition, FilterRule


# ── Resolver dispatch ────────────────────────────────────────────────


def test_resolve_filter_thunderbird_msgfilter(tmp_path: Path) -> None:
    account = {
        "_id": "test",
        "email": "x@example.com",
        "filter": {
            "kind": "thunderbird-msgfilter",
            "filter_paths": [str(tmp_path / "msgFilterRules.dat")],
        },
    }
    f = resolve_filter(account)
    assert f is not None
    assert isinstance(f, MailboxFilter)
    assert isinstance(f, ThunderbirdMsgFilter)


def test_resolve_filter_all_inkl_procmail() -> None:
    account = {
        "_id": "work",
        "email": "x@example.com",
        "filter": {"kind": "all-inkl-procmail", "imap_pass_env": "FAKE_PASS"},
    }
    f = resolve_filter(account)
    assert f is not None
    # Don't construct the http session — just confirm dispatch worked.
    assert type(f).__name__ == "AllInklProcmailFilter"


def test_resolve_filter_gmail_api() -> None:
    account = {"_id": "g", "email": "y@gmail.com", "filter": {"kind": "gmail-api"}}
    f = resolve_filter(account)
    assert f is not None
    assert type(f).__name__ == "GmailFilter"


def test_resolve_filter_unknown_kind_returns_none() -> None:
    account = {"_id": "x", "filter": {"kind": "made-up-backend"}}
    assert resolve_filter(account) is None


def test_resolve_filter_no_kind_returns_none() -> None:
    assert resolve_filter({}) is None
    assert resolve_filter({"filter": {}}) is None


def test_resolve_reader_thunderbird_mbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub thunderbird_profile so the resolver can build an absolute path.
    from core import config

    monkeypatch.setattr(config.CONFIG.personal, "thunderbird_profile", str(tmp_path))

    account = {
        "_id": "test",
        "email": "x@example.com",
        "reader": {"kind": "thunderbird-mbox", "mbox_paths": ["INBOX.mbox"]},
    }
    r = resolve_reader(account)
    assert r is not None
    assert isinstance(r, MailboxReader)
    assert isinstance(r, ThunderbirdMboxReader)


def test_resolve_reader_gmail_api_returns_reader_after_s03() -> None:
    """S03 landed GmailReader; resolver dispatches gmail-api reader-side."""
    account = {"_id": "g", "reader": {"kind": "gmail-api"}}
    r = resolve_reader(account)
    assert r is not None
    assert isinstance(r, MailboxReader)
    assert type(r).__name__ == "GmailReader"


# ── Thunderbird .dat translation round-trip ──────────────────────────


def test_filter_rule_to_dat_and_back() -> None:
    original = FilterRule(
        name="test-newsletter",
        condition=FilterCondition(
            from_addrs=("alice@example.com", "bob@example.com"),
            subject_contains=("[Newsletter]",),
        ),
        action=FilterAction(kind="move", target="INBOX/Newsletters"),
    )
    dr = _to_dat_rule(original)
    assert "OR" in dr.condition
    assert "alice@example.com" in dr.condition
    assert "[Newsletter]" in dr.condition
    assert dr.actions == [("Move to folder", "INBOX/Newsletters")]

    # Round-trip back.
    fr = _from_dat_rule(dr)
    assert fr is not None
    assert fr.name == "test-newsletter"
    assert "alice@example.com" in fr.condition.from_addrs
    assert "bob@example.com" in fr.condition.from_addrs
    assert fr.condition.subject_contains == ("[Newsletter]",)
    assert fr.action.kind == "move"
    assert fr.action.target == "INBOX/Newsletters"


def test_thunderbird_msgfilter_apply_dry_run(tmp_path: Path) -> None:
    filter_file = tmp_path / "msgFilterRules.dat"
    f = ThunderbirdMsgFilter("test", [filter_file])
    rule = FilterRule(
        name="r1",
        condition=FilterCondition(from_addrs=("a@b.c",)),
        action=FilterAction(kind="move", target="INBOX/X"),
    )
    result = f.apply(rule, dry_run=True)
    assert result.success
    assert result.dry_run
    assert "would write" in result.message.lower()
    # No file written on dry-run.
    assert not filter_file.exists()


def test_thunderbird_msgfilter_apply_writes_and_lists(tmp_path: Path) -> None:
    filter_file = tmp_path / "msgFilterRules.dat"
    f = ThunderbirdMsgFilter("test", [filter_file])
    rule = FilterRule(
        name="r1",
        condition=FilterCondition(from_addrs=("a@b.c",)),
        action=FilterAction(kind="move", target="INBOX/X"),
    )
    result = f.apply(rule, dry_run=False)
    assert result.success
    assert filter_file.exists()
    content = filter_file.read_text()
    assert 'name="r1"' in content
    assert "a@b.c" in content
    # list_existing round-trips the rule.
    existing = f.list_existing()
    assert any(e.name == "r1" for e in existing)


# ── ConfigError on legacy schema ─────────────────────────────────────


def test_config_error_on_legacy_account_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy_yaml = tmp_path / "legacy.yaml"
    legacy_yaml.write_text(
        "personal:\n"
        "  accounts:\n"
        "    work:\n"
        "      email: x@example.com\n"
        "      mbox_paths: [INBOX.mbox]\n"
        "      has_procmail: true\n",
        encoding="utf-8",
    )

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", legacy_yaml)
    with pytest.raises(config.ConfigError) as exc:
        config.load()
    msg = str(exc.value)
    assert "legacy" in msg.lower()
    assert "mbox_paths" in msg or "has_procmail" in msg
    assert "Migration template" in msg


def test_new_schema_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new_yaml = tmp_path / "new.yaml"
    new_yaml.write_text(
        "personal:\n"
        "  accounts:\n"
        "    work:\n"
        "      email: x@example.com\n"
        "      reader: { kind: thunderbird-mbox, mbox_paths: [INBOX.mbox] }\n"
        "      filter: { kind: all-inkl-procmail, imap_pass_env: WORK_PASS }\n",
        encoding="utf-8",
    )

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", new_yaml)
    cfg = config.load()
    assert "work" in cfg.personal.accounts
    assert cfg.personal.accounts["work"]["reader"]["kind"] == "thunderbird-mbox"


# ── Reader: date normalisation ───────────────────────────────────────


def test_reader_skips_undated_messages_when_since_set(tmp_path: Path) -> None:
    """Date-header handling across the two scan modes.

    Unfiltered scan: undated messages are included, and the epoch fallback
    is tz-aware so `min()`/`max()` in the report renderers never hit the
    naive-vs-aware TypeError.

    Delta mode (`since` set): undated messages are skipped — they can't be
    placed relative to the watermark, so including them would re-report the
    same messages in every incremental run forever (the legacy scan-email.py
    skipped them explicitly: "unknown date, skip in delta mode").
    """
    import mailbox
    from datetime import datetime, timezone

    box = mailbox.mbox(str(tmp_path / "INBOX"))
    dated = mailbox.mboxMessage()
    dated["From"] = "alice@example.com"
    dated["Subject"] = "dated"
    dated["Date"] = "Mon, 11 May 2026 10:00:00 +0000"
    dated.set_payload("body")
    undated = mailbox.mboxMessage()
    undated["From"] = "bob@example.com"
    undated["Subject"] = "undated"  # no Date header
    undated.set_payload("body")
    box.add(dated)
    box.add(undated)
    box.flush()

    reader = ThunderbirdMboxReader("testacct", [tmp_path])

    # Unfiltered: both messages, all dates tz-aware (no naive epoch).
    metas = list(reader.scan_metadata())
    assert {m.subject for m in metas} == {"dated", "undated"}
    assert all(m.date.tzinfo is not None for m in metas)

    # Delta mode: the undated message is dropped — only the dated one passes.
    recent = list(reader.scan_metadata(since=datetime(2026, 5, 1, tzinfo=timezone.utc)))
    assert {m.subject for m in recent} == {"dated"}


# ── Folder-alias resolution (INBOX vs INBOX-N) ───────────────────────


def test_resolve_folder_alias_finds_inbox_dash_n_when_canonical_missing(tmp_path: Path) -> None:
    """Thunderbird locally aliases re-subscribed folders with -N suffix.

    Reproduces the 2026-05-16 incident: kasserver vault config used
    `INBOX/Vertraege` but on-disk layout had only `INBOX-1.sbd/Vertraege`
    (canonical `INBOX.sbd/` directory did not exist). Pre-fix, scan_deep
    silently returned 0 messages.
    """
    # Simulate Thunderbird's on-disk layout: INBOX-1 file + INBOX-1.sbd/
    (tmp_path / "INBOX-1").touch()
    (tmp_path / "INBOX-1.sbd").mkdir()
    (tmp_path / "INBOX-1.sbd" / "Vertraege").touch()

    reader = ThunderbirdMboxReader("testacct", [tmp_path])

    # Canonical config-style path resolves to the on-disk alias.
    assert reader._resolve_folder_alias("INBOX/Vertraege") == "INBOX-1/Vertraege"
    assert reader._resolve_folder_alias("INBOX") == "INBOX-1"
    # Unrelated path stays unchanged (no alias probing needed).
    assert reader._resolve_folder_alias("Other/Folder") == "Other/Folder"


def test_resolve_folder_alias_no_op_when_canonical_present(tmp_path: Path) -> None:
    """When INBOX exists canonically, alias resolution is a pass-through."""
    (tmp_path / "INBOX").touch()
    (tmp_path / "INBOX.sbd").mkdir()
    (tmp_path / "INBOX.sbd" / "Sub").touch()
    # Even if INBOX-1 also exists (operator hasn't cleaned up), canonical wins.
    (tmp_path / "INBOX-1").touch()
    (tmp_path / "INBOX-1.sbd").mkdir()

    reader = ThunderbirdMboxReader("testacct", [tmp_path])
    assert reader._resolve_folder_alias("INBOX/Sub") == "INBOX/Sub"
    assert reader._resolve_folder_alias("INBOX") == "INBOX"


def test_scan_deep_finds_messages_via_alias(tmp_path: Path) -> None:
    """End-to-end: scan_deep with canonical name actually retrieves
    messages from the aliased on-disk location."""
    import mailbox
    (tmp_path / "INBOX-1.sbd").mkdir()
    mbox_path = tmp_path / "INBOX-1.sbd" / "Vertraege"
    box = mailbox.mbox(str(mbox_path))
    msg = mailbox.mboxMessage()
    msg["From"] = "contract@example.com"
    msg["Subject"] = "Test contract"
    msg["Date"] = "Mon, 11 May 2026 10:00:00 +0000"
    msg.set_payload("body of the contract email")
    box.add(msg)
    box.flush()

    reader = ThunderbirdMboxReader("testacct", [tmp_path])
    messages = list(reader.scan_deep("INBOX/Vertraege"))
    assert len(messages) == 1
    assert messages[0].meta.subject == "Test contract"
