"""Tests for the audio-transcription extension of the voice collector
(M026, 2026-05-28).

Verifies that audio files (.m4a / .wav / .mp3 / …) are routed through
whisper.cpp via subprocess and produce the same `raw/voice/*.md` output
shape as text dictation. Failures (missing model, missing binary,
subprocess error) must leave the source file in the inbox so the
operator can retry once setup is healthy.

All subprocess calls are mocked — these tests must not depend on a
locally-installed whisper-cli, ffmpeg, or model file.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def voice_env(tmp_path, monkeypatch):
    """Tmpdir inbox + tmpdir vault, audio transcription configured.

    Mirrors the fixture in test_voice_collector.py but additionally sets
    the four transcription knobs so audio files can route through the
    (mocked) whisper-cli pipeline. The whisper-cli / ffmpeg binaries
    themselves are mocked at the subprocess.run level per-test.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    vault_raw = tmp_path / "vault" / "raw"
    vault_raw.mkdir(parents=True)
    model = tmp_path / "fake-model.bin"
    model.write_bytes(b"fake-ggml-model")
    fake_whisper = tmp_path / "whisper-cli"
    fake_whisper.write_text("#!/bin/sh\necho mocked\n")
    fake_whisper.chmod(0o755)
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("#!/bin/sh\nexit 0\n")
    fake_ffmpeg.chmod(0o755)

    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", str(inbox))
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_model", str(model))
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_binary", str(fake_whisper))
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_ffmpeg", str(fake_ffmpeg))
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_language", "de")
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_threads", 2)
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)
    monkeypatch.setattr(CONFIG.features, "voice_punctuate", False)

    from collectors import voice as voice_mod
    importlib.reload(voice_mod)

    return voice_mod, voice_mod.VoiceCollector(), inbox, vault_raw / "voice"


def _make_mock_run(transcript: str):
    """Build a subprocess.run mock that returns `transcript` on whisper-cli
    invocation and exits 0 on ffmpeg invocation.

    The dispatcher inspects argv[0] to tell the two binaries apart.
    """
    def fake_run(argv, **kwargs):
        binary = Path(argv[0]).name
        if binary.startswith("whisper"):
            return subprocess.CompletedProcess(argv, 0, stdout=transcript + "\n", stderr="")
        # ffmpeg: produce the requested output file so downstream code
        # doesn't choke. argv tail is `-i src ... -ar ... output.wav`.
        out_path = Path(argv[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-wav")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    return fake_run


# ── Suffix detection ─────────────────────────────────────────────────


def test_scan_inbox_includes_audio_files(voice_env):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    (inbox / "voice.wav").write_bytes(b"fake-wav")
    (inbox / "rec.mp3").write_bytes(b"fake-mp3")
    (inbox / "note.txt").write_text("dictation")
    (inbox / "skip.jpg").write_bytes(b"fake-jpg")

    found = voice_mod._scan_inbox(inbox)
    names = sorted(p.name for p in found)
    assert names == ["memo.m4a", "note.txt", "rec.mp3", "voice.wav"]


# ── Happy path ───────────────────────────────────────────────────────


def test_m4a_routes_through_ffmpeg_and_whisper(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo-de.m4a").write_bytes(b"fake-m4a")
    monkeypatch.setattr(voice_mod.subprocess, "run", _make_mock_run("Dies ist ein Test."))

    result = coll.run()

    assert len(result.files_written) == 1
    assert result.errors == ()
    out = next(raw_voice.iterdir())
    body = out.read_text()
    assert "type: voice-note" in body
    assert "Dies ist ein Test." in body
    assert "source: memo-de.m4a" in body
    # Source archived under raw/inbox-mobile/voice/ (M022 two-zone).
    assert (voice_mod.MOBILE_ARCHIVE_DIR / "memo-de.m4a").exists()
    assert list(inbox.iterdir()) == []


def test_mp3_skips_ffmpeg_native_whisper_format(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "rec.mp3").write_bytes(b"fake-mp3")

    calls: list[list[str]] = []

    def tracking_run(argv, **kwargs):
        calls.append([Path(argv[0]).name, *argv[1:3]])
        binary = Path(argv[0]).name
        if binary.startswith("whisper"):
            return subprocess.CompletedProcess(argv, 0, stdout="Hello.\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(voice_mod.subprocess, "run", tracking_run)

    result = coll.run()

    assert len(result.files_written) == 1
    # Only whisper-cli should have been invoked — no ffmpeg pre-conversion.
    assert [c[0] for c in calls] == ["whisper-cli"]


def test_audio_transcript_runs_through_punctuate_when_enabled(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.features, "voice_punctuate", True)
    monkeypatch.setattr(voice_mod, "_punctuate", lambda raw: "Dies ist ein Test.")
    monkeypatch.setattr(voice_mod.subprocess, "run", _make_mock_run("dies ist ein test"))

    result = coll.run()

    out = next(raw_voice.iterdir())
    body = out.read_text()
    # Cleaned body (capitalized + punctuation) is the rendered text;
    # raw whisper output preserved under raw_transcript: frontmatter.
    assert "Dies ist ein Test." in body
    assert "raw_transcript: |" in body
    assert "dies ist ein test" in body
    assert result.errors == ()


# ── Failure modes leave file in inbox ────────────────────────────────


def test_audio_with_empty_model_path_leaves_file_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_model", "")

    result = coll.run()

    assert result.files_written == ()
    assert any("transcription unavailable" in e for e in result.errors)
    # Source stays in inbox for retry-once-setup-is-healthy.
    assert (inbox / "memo.m4a").exists()
    assert not raw_voice.exists() or list(raw_voice.iterdir()) == []


def test_audio_with_missing_model_file_leaves_file_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_model", "/nonexistent/model.bin")

    result = coll.run()

    assert result.files_written == ()
    assert (inbox / "memo.m4a").exists()


def test_audio_with_missing_whisper_binary_leaves_file_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    from core.config import CONFIG
    monkeypatch.setattr(CONFIG.personal, "voice_transcribe_binary", "/nonexistent/whisper-cli")
    # Force `shutil.which` lookup to also miss so the fallback can't rescue.
    monkeypatch.setattr(voice_mod.shutil, "which", lambda name: None)

    result = coll.run()

    assert result.files_written == ()
    assert (inbox / "memo.m4a").exists()


def test_audio_with_whisper_subprocess_error_leaves_file_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")

    def fake_run(argv, **kwargs):
        binary = Path(argv[0]).name
        if binary.startswith("whisper"):
            raise subprocess.CalledProcessError(returncode=2, cmd=argv, stderr="model load failed")
        out_path = Path(argv[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-wav")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    monkeypatch.setattr(voice_mod.subprocess, "run", fake_run)

    result = coll.run()

    assert result.files_written == ()
    assert (inbox / "memo.m4a").exists()


def test_audio_with_ffmpeg_error_leaves_m4a_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")

    def fake_run(argv, **kwargs):
        binary = Path(argv[0]).name
        if not binary.startswith("whisper"):
            raise subprocess.CalledProcessError(returncode=1, cmd=argv, stderr=b"format unsupported")
        # Whisper should never be reached because ffmpeg failed first.
        raise AssertionError("whisper-cli should not be called when ffmpeg fails")
    monkeypatch.setattr(voice_mod.subprocess, "run", fake_run)

    result = coll.run()

    assert result.files_written == ()
    assert (inbox / "memo.m4a").exists()


def test_audio_with_empty_whisper_stdout_leaves_file_in_inbox(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    monkeypatch.setattr(voice_mod.subprocess, "run", _make_mock_run(""))

    result = coll.run()

    assert result.files_written == ()
    assert (inbox / "memo.m4a").exists()


# ── Mixed batch: text + audio together ───────────────────────────────


def test_mixed_text_and_audio_batch(voice_env, monkeypatch):
    voice_mod, coll, inbox, raw_voice = voice_env
    (inbox / "memo.m4a").write_bytes(b"fake-m4a")
    (inbox / "dictation.txt").write_text("Text dictation works regardless of audio setup.")
    monkeypatch.setattr(voice_mod.subprocess, "run", _make_mock_run("Audio transcript."))

    result = coll.run()

    assert len(result.files_written) == 2
    bodies = sorted(p.read_text() for p in raw_voice.iterdir())
    joined = "\n".join(bodies)
    assert "Audio transcript." in joined
    assert "Text dictation works regardless of audio setup." in joined
