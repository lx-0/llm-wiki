"""Unit tests for the shared collector harness (collectors/base.py).

Two seams, extracted from the copy-paste across the substrate collectors:

- **Account-loop harness** — `resolve_accounts` (kind-discriminated resolver),
  `filter_accounts` (--account), `migrate_flat_state` (legacy flat -> default
  bucket), `Watermark` (advance-on-success / hold-on-failure), and
  `run_account_loop` (failure isolation + message aggregation + save-if-touched
  signal, payload-generic).
- **Inbox-intake harness** — `scan_inbox` (suffix filter, mtime sort),
  `archive_to_zone` (two-zone move with collision policy), `append_rollup`
  (swallowed-failure daily rollup).

These are the invariants that used to live only as parallel comments in 5+3
collectors; testing them here is the point of the extraction.
"""

from __future__ import annotations

import logging
import os

from collectors import base

log = logging.getLogger("test-harness")


# ── Watermark ────────────────────────────────────────────────────────


def test_watermark_advances_on_higher_candidate():
    wm = base.Watermark.seed("2026-05-01T00:00:00Z")
    wm.observe("2026-05-03T00:00:00Z")
    assert wm.value == "2026-05-03T00:00:00Z"
    assert wm.advanced is True


def test_watermark_holds_when_no_higher_candidate():
    wm = base.Watermark.seed("2026-05-10T00:00:00Z")
    wm.observe("2026-05-01T00:00:00Z")  # older
    wm.observe(None)  # ignored
    assert wm.value == "2026-05-10T00:00:00Z"
    assert wm.advanced is False


def test_watermark_from_empty_seed_advances_on_first_observe():
    wm = base.Watermark.seed(None)
    assert wm.advanced is False
    wm.observe("2026-05-01T00:00:00Z")
    assert wm.value == "2026-05-01T00:00:00Z"
    assert wm.advanced is True


def test_watermark_equal_candidate_does_not_advance():
    wm = base.Watermark.seed("2026-05-05T00:00:00Z")
    wm.observe("2026-05-05T00:00:00Z")
    assert wm.advanced is False


# ── resolve_accounts ─────────────────────────────────────────────────


def test_resolve_accounts_picks_only_matching_kind():
    accounts = {
        "work": {"gmeet": {"kind": "gmeet-api", "drive_folder_id": "F1"}},
        "private": {"gmeet": {"kind": "something-else"}},
        "misc": {"jamie": {"kind": "jamie-api"}},  # different block key
    }
    got = base.resolve_accounts(
        accounts,
        "gmeet-api",
        lambda aid, block: (aid, block.get("drive_folder_id")),
        block_key="gmeet",
    )
    assert got == [("work", "F1")]


def test_resolve_accounts_nested_block_key():
    accounts = {
        "me": {"health": {"oura": {"kind": "oura-pat", "api_key_env": "OURA"}}},
        "other": {"health": {"healthkit": {"kind": "healthkit-xml-export"}}},
    }
    oura = base.resolve_accounts(
        accounts, "oura-pat", lambda aid, block: aid, block_key=("health", "oura")
    )
    hk = base.resolve_accounts(
        accounts, "healthkit-xml-export", lambda aid, block: aid,
        block_key=("health", "healthkit"),
    )
    assert oura == ["me"]
    assert hk == ["other"]


def test_resolve_accounts_skips_non_dict_bodies():
    accounts = {"broken": "not-a-dict", "ok": {"gmeet": {"kind": "gmeet-api"}}}
    got = base.resolve_accounts(accounts, "gmeet-api", lambda aid, block: aid, block_key="gmeet")
    assert got == ["ok"]


def test_resolve_accounts_empty_config_is_graceful():
    assert base.resolve_accounts({}, "gmeet-api", lambda aid, b: aid, block_key="gmeet") == []


# ── filter_accounts ──────────────────────────────────────────────────


class _Acct:
    def __init__(self, account_id):
        self.account_id = account_id


def test_filter_accounts_none_returns_all():
    accts = [_Acct("work"), _Acct("private")]
    assert base.filter_accounts(accts, None) == accts


def test_filter_accounts_matches_single_id():
    accts = [_Acct("work"), _Acct("private")]
    got = base.filter_accounts(accts, "private")
    assert [a.account_id for a in got] == ["private"]


def test_filter_accounts_unknown_id_returns_empty():
    assert base.filter_accounts([_Acct("work")], "nope") == []


def test_filter_accounts_custom_id_of_for_tuples():
    tuples = [("work", {}, object()), ("private", {}, object())]
    got = base.filter_accounts(tuples, "work", id_of=lambda t: t[0])
    assert [t[0] for t in got] == ["work"]


# ── migrate_flat_state ───────────────────────────────────────────────


def test_migrate_flat_state_folds_flat_into_default():
    state = {"last_seen_ts": "2026-05-01T00:00:00Z"}
    base.migrate_flat_state(state, "last_seen_ts", log=log, name="T")
    assert state == {"default": {"last_seen_ts": "2026-05-01T00:00:00Z"}}


def test_migrate_flat_state_noop_when_per_account_bucket_exists():
    state = {"work": {"last_seen_ts": "2026-05-01T00:00:00Z"}}
    base.migrate_flat_state(state, "last_seen_ts", log=log, name="T")
    assert state == {"work": {"last_seen_ts": "2026-05-01T00:00:00Z"}}


def test_migrate_flat_state_noop_when_empty():
    state: dict = {}
    base.migrate_flat_state(state, "last_seen_ts", log=log, name="T")
    assert state == {}


# ── run_account_loop ─────────────────────────────────────────────────


def test_run_account_loop_aggregates_payloads_and_messages():
    accts = [_Acct("work"), _Acct("private")]

    def scan(acct):
        return (f"scanned {acct.account_id}", [acct.account_id], True)

    outcome = base.run_account_loop(accts, scan, log=log, name="T")
    assert outcome.payloads == [["work"], ["private"]]
    assert outcome.messages == ["work: scanned work", "private: scanned private"]
    assert outcome.any_state_touched is True
    assert outcome.error_ids == []


def test_run_account_loop_isolates_one_failing_account():
    accts = [_Acct("boom"), _Acct("ok")]

    def scan(acct):
        if acct.account_id == "boom":
            raise RuntimeError("kaboom")
        return ("fine", ["ok"], False)

    outcome = base.run_account_loop(accts, scan, log=log, name="T")
    # The good account still ran.
    assert outcome.payloads == [["ok"]]
    assert outcome.error_ids == ["boom"]
    assert any("ERROR RuntimeError: kaboom" in m for m in outcome.messages)
    assert outcome.messages[0].startswith("boom: ERROR")


def test_run_account_loop_state_touched_is_or_over_accounts():
    accts = [_Acct("a"), _Acct("b")]

    def scan(acct):
        return ("m", None, acct.account_id == "b")  # only b touched state

    outcome = base.run_account_loop(accts, scan, log=log, name="T")
    assert outcome.any_state_touched is True


def test_run_account_loop_describe_controls_message_label():
    accts = [_Acct("me")]

    def scan(acct):
        return ("done", None, False)

    outcome = base.run_account_loop(
        accts, scan, log=log, name="Health",
        describe=lambda a: f"{a.account_id} oura",
    )
    assert outcome.messages == ["me oura: done"]


# ── scan_inbox ───────────────────────────────────────────────────────


def test_scan_inbox_filters_and_sorts_by_mtime(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "a.txt").write_text("a")
    (inbox / "b.txt").write_text("b")
    (inbox / ".hidden").write_text("dot")
    (inbox / "photo.jpg").write_text("wrong suffix")
    (inbox / "sub").mkdir()
    os.utime(inbox / "a.txt", (2000, 2000))
    os.utime(inbox / "b.txt", (1000, 1000))  # older -> comes first

    got = base.scan_inbox(inbox, (".txt", ".md"))
    assert [p.name for p in got] == ["b.txt", "a.txt"]


def test_scan_inbox_case_insensitive_suffix(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "shout.TXT").write_text("x")
    assert [p.name for p in base.scan_inbox(inbox, (".txt",))] == ["shout.TXT"]


def test_scan_inbox_missing_dir_is_empty(tmp_path):
    assert base.scan_inbox(tmp_path / "nope", (".txt",)) == []


# ── archive_to_zone ──────────────────────────────────────────────────


def test_archive_to_zone_moves_source_into_zone(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hi")
    zone = tmp_path / "zone"
    dest = base.archive_to_zone(src, zone)
    assert dest == zone / "note.txt"
    assert dest.exists()
    assert not src.exists()


def test_archive_to_zone_collision_gets_mtime_suffix(tmp_path):
    zone = tmp_path / "zone"
    zone.mkdir()
    (zone / "note.txt").write_text("existing archive")  # occupy the name
    src = tmp_path / "note.txt"
    src.write_text("new drop")
    os.utime(src, (1234567, 1234567))
    dest = base.archive_to_zone(src, zone)
    assert dest.name == "note-1234567.txt"  # suffixed, no clobber
    assert (zone / "note.txt").read_text() == "existing archive"
    assert dest.read_text() == "new drop"


# ── append_rollup ────────────────────────────────────────────────────


def test_append_rollup_uses_plain_append_without_source_ref(monkeypatch):
    from core import daily_capture

    calls = []
    monkeypatch.setattr(daily_capture, "append", lambda *a: calls.append(("append", a)))
    monkeypatch.setattr(
        daily_capture, "append_with_source", lambda *a: calls.append(("with_source", a))
    )
    base.append_rollup("2026-05-01", "captures", "- line")
    assert calls == [("append", ("2026-05-01", "captures", "- line"))]


def test_append_rollup_uses_append_with_source_when_ref_given(monkeypatch):
    from core import daily_capture

    calls = []
    monkeypatch.setattr(daily_capture, "append", lambda *a: calls.append(("append", a)))
    monkeypatch.setattr(
        daily_capture, "append_with_source", lambda *a: calls.append(("with_source", a))
    )
    base.append_rollup("2026-05-01", "voice", "- line", source_ref="raw/voice/x.md")
    assert calls == [("with_source", ("2026-05-01", "voice", "- line", "raw/voice/x.md"))]


def test_append_rollup_swallows_failures(monkeypatch):
    from core import daily_capture

    def _boom(*_a):
        raise RuntimeError("daily write failed")

    monkeypatch.setattr(daily_capture, "append", _boom)
    # Must not raise — the rollup is a side-effect.
    base.append_rollup("2026-05-01", "pictures", "- line", context="picture x")
