"""Direct Wispr HTTP contract, retry/dedup and no-write guarantees."""
import json
from types import SimpleNamespace

import httpx
import pytest

from collectors import wispr

MID = "11111111-1111-4111-8111-111111111111"
MID2 = "22222222-2222-4222-8222-222222222222"


def meeting(mid=MID, **changes):
    # Field names/types captured from the live /api/v1/meetings/sync response.
    return {
        "id": mid, "title": "Design review", "created_at": "2026-10-08T15:37:03.608000",
        "modified_at": "2026-10-08T15:54:09.043677", "ended_at": "2026-10-08T15:54:08.525000",
        "is_deleted": False, "finalized": True, "is_recording": False,
        "notes": "", "summary": "Decision: ship the collector.",
        "refined_transcript": "[00:01] Alex: Let's ship it.",
        "contacts": [], "transcript_deleted_at": None, **changes,
    }


def page(rows, cursor=None, sync="1791475000000"):
    return {"pull": rows, "acked": [], "rejected": [],
            "sync_time": sync, "next_cursor": cursor}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    state = tmp_path / "state.json"
    limits = SimpleNamespace(wispr_max_per_run=50, wispr_max_pages=100,
                             wispr_request_timeout_s=30)
    account = {"wispr": {"kind": "wispr-api", "access_token_env": "WISPR_TEST_TOKEN"}}
    monkeypatch.setattr(wispr, "CONFIG", SimpleNamespace(
        personal=SimpleNamespace(accounts={"test": account}), limits=limits))
    monkeypatch.setenv("WISPR_TEST_TOKEN", "test-secret")
    monkeypatch.setattr(wispr, "ROOT_DIR", root)
    monkeypatch.setattr(wispr, "_STATE_FILE", state)
    monkeypatch.setattr(wispr.daily_capture, "DAILY_DIR", root / "daily")
    return root, state, limits


def mock_client(monkeypatch, pages):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        assert request.url == "https://api.wisprflow.ai/api/v1/meetings/sync"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "test-secret"
        assert body["meetings"] == []  # never upload a source row
        assert "recording_states" not in body
        assert body["supports_refined_stamp_fetch"] is False
        calls.append(body)
        result = pages[min(len(calls)-1, len(pages)-1)]
        return httpx.Response(result if isinstance(result, int) else 200,
                              json={} if isinstance(result, int) else result)
    original = wispr.WisprClient
    monkeypatch.setattr(wispr, "WisprClient", lambda a: original(a, transport=httpx.MockTransport(handle)))
    return calls


def test_import_dedup_update_and_provenance(env, monkeypatch):
    root, state, _ = env
    mock_client(monkeypatch, [page([meeting()])])
    first = wispr.WisprCollector().run()
    assert not first.errors and len(first.files_written) == 1
    target = first.files_written[0]
    text = target.read_text()
    assert "## Summary" in text and "## Transcript" in text
    assert "test-secret" not in text
    daily = next((root / "daily").glob("*/meetings.md"))
    assert "sources:" in daily.read_text() and "[[" not in daily.read_text()
    again = wispr.WisprCollector().run(incremental=True)
    assert not again.files_written and again.files_skipped == 1
    assert json.loads(state.read_text())["test"]["sync_time"] == "1791475000000"


def test_title_changes_keep_path(env, monkeypatch):
    root, _, _ = env
    pages = [page([meeting()])]
    mock_client(monkeypatch, pages)
    first = wispr.WisprCollector().run().files_written[0]
    pages[0] = page([meeting(title="Renamed", refined_transcript="Updated words")])
    second = wispr.WisprCollector().run().files_written[0]
    assert first == second and "Updated words" in second.read_text()
    assert len(list((root / wispr._OUTPUT).glob("*.md"))) == 1
    assert next((root / "daily").glob("*/meetings.md")).read_text().count("**wispr**") == 1


def test_dry_run_has_no_writes(env, monkeypatch):
    root, state, _ = env
    mock_client(monkeypatch, [page([meeting()])])
    result = wispr.WisprCollector().run(dry_run=True)
    assert "1 would write" in result.message and not result.errors
    assert not root.exists() and not state.exists() and not state.with_suffix(".lock").exists()


def test_empty_and_recording_are_retried(env, monkeypatch):
    root, state, _ = env
    mock_client(monkeypatch, [page([
        meeting(summary=None, refined_transcript=None),
        meeting(MID2, is_recording=True),
    ])])
    result = wispr.WisprCollector().run(incremental=True)
    assert "2 pending" in result.message and not result.files_written
    assert json.loads(state.read_text())["test"]["sync_time"] == "0"
    assert not root.exists()


def test_multiple_pages_and_cursor(env, monkeypatch):
    _, state, _ = env
    calls = mock_client(monkeypatch, [page([meeting()], "next"), page([meeting(MID2)])])
    result = wispr.WisprCollector().run()
    assert len(result.files_written) == 2 and not result.errors
    assert calls[1]["cursor"] == "next"
    assert json.loads(state.read_text())["test"]["sync_time"] != "0"


def test_failed_page_keeps_watermark_and_successful_dedup(env, monkeypatch):
    _, state, _ = env
    mock_client(monkeypatch, [page([meeting()], "next"), 401])
    result = wispr.WisprCollector().run()
    assert result.errors == ("test",)
    saved = json.loads(state.read_text())["test"]
    assert saved["sync_time"] == "0" and MID in saved["items"]


def test_cap_does_not_lose_remainder(env, monkeypatch):
    _, state, limits = env
    limits.wispr_max_per_run = 1
    mock_client(monkeypatch, [page([meeting(), meeting(MID2)])])
    first = wispr.WisprCollector().run(incremental=True)
    assert len(first.files_written) == 1
    assert json.loads(state.read_text())["test"]["sync_time"] == "0"
    second = wispr.WisprCollector().run(incremental=True)
    assert len(second.files_written) == 1 and second.files_skipped == 1
    assert json.loads(state.read_text())["test"]["sync_time"] != "0"


@pytest.mark.parametrize("mode", ["cycle", "limit", "schema"])
def test_incomplete_or_invalid_scan_does_not_advance(env, monkeypatch, mode):
    _, state, limits = env
    if mode == "limit":
        limits.wispr_max_pages = 1
    payload = page([], "repeat") if mode != "schema" else {"sync_time": "1"}
    mock_client(monkeypatch, [payload])
    assert wispr.WisprCollector().run().errors
    assert not state.exists()


def test_auth_session_identity_and_token_rotation(tmp_path):
    path = tmp_path / "session.json"
    data = {"workosSession": {"accessToken": "first", "userId": "u1"}}
    path.write_text(json.dumps(data))
    account = wispr.WisprAccount("work", "", str(path), "u1")
    assert account.token() == "first"
    data["workosSession"]["accessToken"] = "second"
    path.write_text(json.dumps(data))
    assert account.token() == "second"
    data["workosSession"]["userId"] = "another-user"
    path.write_text(json.dumps(data))
    with pytest.raises(wispr.WisprAPIError, match="different"):
        account.token()
    assert json.loads(path.read_text()) == data


def test_deleted_remote_source_does_not_delete_archive(env, monkeypatch):
    pages = [page([meeting()])]
    mock_client(monkeypatch, pages)
    path = wispr.WisprCollector().run().files_written[0]
    pages[0] = page([meeting(is_deleted=True)])
    assert not wispr.WisprCollector().run().files_written
    assert path.exists()


def test_lexical_and_timestamp(monkeypatch):
    monkeypatch.setattr(wispr, "TIMEZONE", "Europe/Berlin")
    notes = json.dumps({"root": {"type": "root", "children": [
        {"type": "paragraph", "children": [{"type": "text", "text": "A decision"}]}]}})
    assert wispr._text(notes) == "A decision"
    fm, _, date, _ = wispr._render(meeting(created_at="2026-10-08T23:30:00Z"), "test")
    assert date == "2026-10-09"
    assert wispr._date("2026-10-08T15:37:03.608000") == wispr._date("1791473823608")
    with pytest.raises(ValueError):
        wispr._render(meeting(id="../../escape"), "test")


def test_empty_live_response(env, monkeypatch):
    _, state, _ = env
    mock_client(monkeypatch, [page([meeting(
        notes="", summary=None, refined_transcript=None,
        transcript_ready=False, summary_ready=False,
    )], sync="0")])
    result = wispr.WisprCollector().run()
    assert not result.errors and not result.files_written
    assert "1 pending" in result.message


def test_sync_watermark_anchors_to_first_page(env, monkeypatch):
    _, state, _ = env
    mock_client(monkeypatch, [page([], "next", "10"), page([], sync="20")])
    assert not wispr.WisprCollector().run().errors
    assert json.loads(state.read_text())["test"]["sync_time"] == "10"
