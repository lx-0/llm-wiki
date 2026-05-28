---
title: Voice intake collector
status: durchstich-shipped
captured: 2026-05-15
related: [[jamie-intake]], [[gmeet-collector]], [[gbrain-comparison]]
---

# Voice intake

## Premise

Operator dictates → text lands as a raw note in `<vault>/raw/voice/` →
existing `compile.py` distills into knowledge articles. Fifth substrate
after email / jamie / gmeet / youtube.

## What gbrain does (reference)

`garrytan/gbrain` ships a `voice-note-ingest` skill but **does not bundle a
dictation client**. It accepts whatever transcript the host agent hands it
and falls back to Groq Whisper / OpenAI for transcoding. Same posture as
our jamie + gmeet collectors: substrate-agnostic on the capture side,
opinionated on the storage side.

Implication: we don't pick a dictation tool. We pick an inbox shape and
let the operator wire any tool that writes text files into it.

## Landscape (verified 2026-05-15)

Survivors of the source-available / FOSS macOS dictation field:

| Repo                          |    ★ | License            | Notes                                          |
| ----------------------------- | ---: | ------------------ | ---------------------------------------------- |
| Beingpax/VoiceInk             |   5k | GPLv3 + commercial | Polished, fork-only, no PRs accepted           |
| OpenWhispr/openwhispr         | 3.1k | MIT                | x-platform, local Parakeet+Whisper, BYOK cloud |
| altic-dev/FluidVoice          | 2.2k | GPLv3              | macOS-native Swift, pure-local                 |
| FluidInference/FluidAudio     |   2k | Apache-2.0         | CoreML STT lib — engine, not app               |
| zachlatta/freeflow            | 1.7k | MIT                | Groq-API only — vendor lock-in                 |
| silverstein/minutes           | 1.2k | MIT                | Voice-note + meeting + searchable              |
| TypeWhisper/typewhisper-mac   | 1.2k | GPLv3              | Active, optional cloud                         |
| Starmel/OpenSuperWhisper      |  780 | MIT                | Clean MIT Whisper.cpp wrapper                  |
| moinulmoin/voicetypr          |  375 | "Other"            | Tauri/Rust, source-available                   |
| PinW/whisper-key-local        |  153 | MIT                | Hotkey → cursor                                |
| t2o2/local-whisper            |   27 | MIT                | macOS Apple Silicon, minimal                   |

Dropped: knowall-ai/turbo-whisper (Linux-only, dead-ish).

## Pick

**OpenWhispr** for the operator-side tool — only candidate that is
simultaneously truly MIT, cross-platform, has local Parakeet+Whisper
*and* BYOK cloud, no commercial-license trap. Runner-up: **FluidVoice**
(macOS-native, pure-local, GPLv3) if cross-platform doesn't matter.

The collector accepts any tool; OpenWhispr is the *default
recommendation*, not a dependency.

## Architecture (shipped durchstich)

Single config knob, no multi-tenant:

```yaml
personal:
  voice_inbox: "~/VoiceIntake"   # any writable directory; "" disables
```

Collector behaviour (`scripts/collectors/voice.py`):

1. Scan `voice_inbox` (non-recursive) for `*.txt` and `*.md`.
2. For each file: read content, slug-name it, write to
   `<vault>/raw/voice/voice-YYYY-MM-DD-HHMM-<slug>.md` with frontmatter:

   ```yaml
   type: voice-note
   origin: voice-intake
   captured_at: <source mtime, ISO>
   source: <original basename>
   tags: [voice]
   ```

3. Move the source into `<voice_inbox>/.processed/` (preserves originals,
   makes re-runs idempotent without a state file).
4. Files starting with `.` and the `.processed/` dir itself are ignored.

Piggyback default: `True`, cooldown 1 h (voice is time-sensitive).
`is_configured()` returns False when `voice_inbox` is empty or missing →
graceful agnostic, no error.

## Operator setup

**Mobile primary (2026-05-15 pivot):** the operator dictates on iPhone,
not Mac. Setup `docs/setup-voice.md` documents the path; TL;DR:

1. `mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/VoiceIntake`
2. Set `personal.voice_inbox` to that iCloud-Drive-synced path.
3. On iPhone, build a Shortcut: *Dictate Text → Save File → iCloud
   Drive/VoiceIntake/voice-<timestamp>.txt*. Bind to Action Button or
   Back Tap.
4. iCloud syncs the file to Mac (~30 s–2 min). Piggyback or
   `wiki collect voice` ingests.

**Engine change for the mobile pivot: zero.** The collector is
path-agnostic; iCloud Drive just happens to be a folder.

**Mac-side alternatives (no engine change either):**

- OpenWhispr: BYOK Whisper / Parakeet, MIT, cross-platform. Best Mac pick.
- FluidVoice: macOS-native Swift, pure-local, GPLv3.
- macOS built-in dictation: hold Fn, paste into a `.txt` in the inbox.
- Hammerspoon snippet: capture clipboard → write timestamped file.
- Aiko (iOS): free, MIT-spirit, on-device Whisper — better quality than
  Apple's native dictation for proper-noun-heavy domains.

## Shipped 2026-05-28 (M026)

- **Audio-file ingestion via whisper.cpp** — `.m4a` / `.mp4` / `.mp3` /
  `.wav` / `.flac` / `.ogg` / `.aac` files dropped into voice_inbox are
  transcribed locally by `collectors/voice.py:_transcribe_audio()`.
  Operator pre-reqs: `brew install whisper-cpp` + a ggml model file
  (`~/whisper-models/ggml-base.bin` from
  https://huggingface.co/ggerganov/whisper.cpp/tree/main). m4a/mp4/aac
  routes through ffmpeg → 16 kHz mono PCM wav first; native formats
  (mp3/wav/flac/ogg) go straight to whisper-cli. Fail-soft: missing
  binary or model leaves the file in inbox and surfaces as a health
  warning rather than an error — text dictation keeps working. Five
  new config knobs under `personal.voice_transcribe_*`; health check
  `voice-audio-setup` flags the half-installed state. The launchd
  watcher on Voice Memos' Group Container is still on the table as a
  separate piece (no inbox involvement — would need its own folder
  watcher or post-process script writing into voice_inbox).

## Deferred (not in durchstich)

- **Voice-note → daily-log pairing** — append short voice notes to the
  current `daily/YYYY-MM-DD.md` instead of a standalone raw file. Wait
  for compile feedback on the first batch before committing.
- **Speaker hint / context tag** — let the operator say
  "context: project-X" as the first line and lift it into frontmatter.
  Premature until a pattern emerges from real notes.
- **Multi-machine inbox** — voice_inbox under iCloud Drive / Syncthing.
  Already works (it's just a path); document once tested.

## Why not write our own dictation client

Every survivor in the table is a thin Whisper/Parakeet wrapper. The
value is in the compile pipeline we already have, not in another
hotkey-to-text app. Same rationale as `meeting-intake-candidates`:
adopt jamie's API instead of building diarisation.
