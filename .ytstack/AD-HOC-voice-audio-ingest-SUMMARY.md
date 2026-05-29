# AD-HOC: Voice collector grows audio transcription via whisper.cpp (2026-05-28)

## Trigger
Operator reported m4a files accumulating in `voice_inbox` on lxw (iOS
Voice Memos + third-party recorders). Pre-2026-05-28 the collector
silently filtered out anything that wasn't `.txt` / `.md` — audio files
sat in the inbox forever with no log line, no health warning.
`.ytstack/backlog/voice-intake.md` had this as the "natural next slice"
with two open questions: which transcription engine, and where to draw
the engine-deps line.

## Decision
**whisper.cpp via subprocess**, operator installs via `brew install
whisper-cpp` + one-time model download. Rejected: faster-whisper as
a Python dep (~150 MB CTranslate2 + ONNX-runtime, runtime model
download from HuggingFace — too "fat" for an offline-first engine),
mlx-whisper (Apple-Silicon-only audience narrow), remote LLM gateway
(no STT endpoint exists in the available endpoints). Full rationale:
DECISIONS 2026-05-28. Matches the engine's posture of "collectors are
thin orchestrators that shell out to external services" (Ollama HTTP,
Claude SDK, Google APIs, now whisper-cli).

## Pipeline
- `.mp3` / `.wav` / `.flac` / `.ogg` → straight to `whisper-cli` (its
  native input formats).
- `.m4a` / `.mp4` / `.aac` → `ffmpeg` first (`-ar 16000 -ac 1 -c:a pcm_s16le`,
  whisper's preferred input shape) into a `TemporaryDirectory` wav,
  then `whisper-cli`.
- Transcript flows downstream same as text dictation: optional
  `voice_punctuate` Ollama pass, daily/<date>/voice.md rollup, canonical
  `raw/voice/voice-<date>-<HHMM>-<slug>.md`.
- Source archives under `raw/inbox-mobile/voice/` (M022 two-zone).

## Fail-soft posture
Empty `voice_transcribe_model`, missing model file, missing whisper-cli
on $PATH, missing ffmpeg, subprocess error, empty stdout — all return
`None` from `_transcribe_audio()`. Collector surfaces "transcription
unavailable, left in inbox" in `errors[]` and leaves the source
untouched so a re-run picks it up once setup is healthy. **Voice
ingest must not break the collector loop.** Text dictation continues
working regardless.

## Operator setup (one-time)
```
brew install whisper-cpp                                    # binary: /opt/homebrew/bin/whisper-cli
mkdir -p ~/whisper-models && cd ~/whisper-models
curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
# then in <vault>/.wiki/config.yaml:
#   personal.voice_transcribe_model: "~/whisper-models/ggml-base.bin"
```

## Config (5 new keys under `personal`, all default empty = disabled)
- `voice_transcribe_model` — path to ggml model file
- `voice_transcribe_language` — `"auto"` / `"de"` / `"en"` / …
- `voice_transcribe_threads` — whisper-cli `-t N` (default 4)
- `voice_transcribe_binary` — explicit path override; empty = `$PATH`
- `voice_transcribe_ffmpeg` — explicit path override; empty = `$PATH`

All five wired through `scripts/migrations/migrate_config_keys.py` per
the CLAUDE.md hard rule (config-knob changes are not done until the vault
is migrated).

## Hotfix: voice_punctuate cold-call timeout (commit `adf5fcd`)
First live run on lxw transcribed both queued m4a files cleanly, but the
**Ollama-driven punctuate pass timed out**. Empirical, after live-probing
the real `http://192.168.2.42:11434` endpoint:

| Call | Latency |
|---|---|
| Cold (model load into VRAM + 2-token reply) | **36 s** |
| Warm (~70-token reply) | **11 s** |

Hardcoded `PUNCTUATE_TIMEOUT_S = 30.0` was the outlier in the file —
sister knobs: `curiosity_timeout_s=240` ("gemma4:e4b on long YT-notes
regularly hits >90 s"), `screenshot_timeout_seconds=60`, `chat()` default
`120`. Lifted to `limits.voice_punctuate_timeout_s` (default 120,
mirrors `chat()`). Migration entry added (CLAUDE.md hard rule).

## Health check
New `check_voice_audio_setup` in `scripts/core/health.py`:
- silent (ok) when no audio files queued — operators without audio
  see no friction.
- WARNING when files queued + half-installed state (empty model knob;
  model knob set + file missing; model OK + whisper-cli not on PATH;
  m4a queued + ffmpeg not on PATH).

## Tests
- 12 new tests in `tests/test_voice_collector_audio.py`, all
  subprocess-mocked (do not require local whisper-cli / ffmpeg / model).
  Suffix detection, m4a → ffmpeg → whisper happy path, mp3 skip-ffmpeg
  native path, punctuate-pass interaction, six fail-soft modes.
- `tests/test_migrate_config_keys.py` round-trip expected-diff count
  bumped to 69 (5 voice_transcribe_* + 1 voice_punctuate_timeout_s).

## Verified end-to-end on lxw
- Setup verified live against `http://192.168.2.42:11434/v1/chat/completions`
  (gemma4:e4b loaded). Two queued m4a files → two `raw/voice/*.md`,
  zero errors, ~13 s total wall-clock after the hotfix.
- Resulting frontmatter carries `raw_transcript: |` (pre-punctuate
  whisper output) with the punctuated text in the body — exactly the
  documented shape.

## Commits
- `0b147bb` — feat(voice): transcribe m4a/wav/mp3/… via whisper.cpp
- `adf5fcd` — fix(voice): bump punctuate Ollama timeout 30s → 120s

## Open / deferred
- Voice Memos `~/Library/Group Containers/.../Recordings/` would need its
  own folder-watcher or export-script writing into `voice_inbox` (still in
  `.ytstack/backlog/voice-intake.md` "Deferred").
- Voice-note → daily-log pairing (operator decision deferred).
