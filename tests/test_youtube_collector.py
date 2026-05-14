"""Tests for `collectors/scan_youtube.py:YoutubeCollector` — Protocol + inbox-drain.

The ingest path is yt-dlp / network-bound, so run()/drain_inbox tests
monkeypatch `_ingest_items` to a canned result. Pure helpers
(parse_inbox, extract_video_id, is_playlist_url) are tested directly.
"""

from __future__ import annotations

from pathlib import Path


# ── Protocol conformance ────────────────────────────────────────────


def test_youtube_collector_registered():
    from collectors import get_collector

    c = get_collector("youtube")
    assert c is not None
    assert c.SPEC.name == "youtube"
    assert c.SPEC.output_subfolder == "raw/notes/youtube"
    assert c.SPEC.piggyback_default is False
    assert c.SPEC.supports_incremental is False


def test_youtube_is_configured_reflects_inbox_file(monkeypatch, tmp_path):
    from collectors import scan_youtube

    inbox = tmp_path / "youtube.md"
    monkeypatch.setattr(scan_youtube, "INBOX_FILE", inbox)
    assert scan_youtube.YoutubeCollector().is_configured() is False

    inbox.write_text("https://youtu.be/dQw4w9WgXcQ\n", encoding="utf-8")
    assert scan_youtube.YoutubeCollector().is_configured() is True


def test_youtube_run_skips_when_no_inbox(monkeypatch, tmp_path):
    from collectors import scan_youtube

    monkeypatch.setattr(scan_youtube, "INBOX_FILE", tmp_path / "missing.md")
    result = scan_youtube.YoutubeCollector().run()
    assert result.files_written == ()
    assert "No YouTube inbox" in result.message


def test_youtube_run_maps_drain_result(monkeypatch, tmp_path):
    from collectors import scan_youtube

    inbox = tmp_path / "youtube.md"
    inbox.write_text("https://youtu.be/aaaaaaaaaaa\nhttps://youtu.be/bbbbbbbbbbb\n", encoding="utf-8")
    monkeypatch.setattr(scan_youtube, "INBOX_FILE", inbox)

    written_a = tmp_path / "video-a.md"
    written_a.write_text("# A", encoding="utf-8")

    def fake_ingest_items(items, **kw):
        # one written, one skipped
        return {
            "written": 1, "skipped": 1, "failed": 0,
            "results": [
                {"video_id": "aaaaaaaaaaa", "status": "written", "path": str(written_a)},
                {"video_id": "bbbbbbbbbbb", "status": "skipped"},
            ],
        }

    monkeypatch.setattr(scan_youtube, "_ingest_items", fake_ingest_items)

    result = scan_youtube.YoutubeCollector().run()
    assert result.files_written == (written_a,)
    assert result.files_skipped == 1  # 2 processed - 1 written
    assert "1 written" in result.message
    assert "1 skipped" in result.message


# ── drain_inbox ─────────────────────────────────────────────────────


def test_drain_inbox_missing_file_is_noop(tmp_path):
    from collectors import scan_youtube

    result = scan_youtube.drain_inbox(tmp_path / "nope.md")
    assert result["processed"] == 0
    assert result["written"] == 0
    assert "no inbox file" in result["message"]


def test_drain_inbox_empty_file(tmp_path):
    from collectors import scan_youtube

    inbox = tmp_path / "youtube.md"
    inbox.write_text("# just a comment\n\n", encoding="utf-8")
    result = scan_youtube.drain_inbox(inbox)
    assert result["processed"] == 0
    assert "is empty" in result["message"]


def test_drain_inbox_processes_items(monkeypatch, tmp_path):
    from collectors import scan_youtube

    inbox = tmp_path / "youtube.md"
    inbox.write_text(
        "https://youtu.be/aaaaaaaaaaa\n"
        "https://www.youtube.com/watch?v=bbbbbbbbbbb\n",
        encoding="utf-8",
    )

    seen = {}

    def fake_ingest_items(items, **kw):
        seen["count"] = len(items)
        seen["input_source"] = kw.get("input_source")
        return {"written": 2, "skipped": 0, "failed": 0,
                "results": [{"status": "written", "path": "/tmp/a.md"},
                            {"status": "written", "path": "/tmp/b.md"}]}

    monkeypatch.setattr(scan_youtube, "_ingest_items", fake_ingest_items)

    result = scan_youtube.drain_inbox(inbox)
    assert seen["count"] == 2
    assert seen["input_source"] == "inbox"
    assert result["processed"] == 2
    assert result["written"] == 2
    assert len(result["report_paths"]) == 2


# ── pure helpers ────────────────────────────────────────────────────


def test_parse_inbox_bare_and_markdown_links():
    from collectors import scan_youtube

    text = (
        "# my watchlist\n"
        "https://youtu.be/aaaaaaaaaaa\n"
        "- [Some title](https://www.youtube.com/watch?v=bbbbbbbbbbb) tier: 2\n"
        "random line without a url\n"
        "https://example.com/not-youtube\n"
    )
    items = scan_youtube.parse_inbox(text)
    # 2 youtube URLs; the non-youtube + textline dropped
    assert len(items) == 2
    assert items[0].url == "https://youtu.be/aaaaaaaaaaa"
    assert "youtube.com/watch?v=bbbbbbbbbbb" in items[1].url
    assert items[1].tier_override == 2


def test_extract_video_id():
    from collectors import scan_youtube

    assert scan_youtube.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert scan_youtube.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert scan_youtube.extract_video_id("https://example.com/x") is None


def test_is_playlist_url():
    from collectors import scan_youtube

    assert scan_youtube.is_playlist_url("https://www.youtube.com/playlist?list=PLxxxx") is True
    assert scan_youtube.is_playlist_url("https://youtu.be/dQw4w9WgXcQ") is False
