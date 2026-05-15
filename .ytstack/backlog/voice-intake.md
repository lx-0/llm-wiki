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

## Operator setup (OpenWhispr path)

Documented in `docs/setup-voice.md`. TL;DR:

1. `mkdir -p ~/VoiceIntake`
2. Install OpenWhispr; configure its "save transcript to file" target to
   `~/VoiceIntake/voice-$(date +%s).txt`.
3. Set `personal.voice_inbox: "~/VoiceIntake"` in
   `<vault>/.wiki/config.yaml`.
4. Either: wait for the piggyback (auto, 1 h cooldown), or run
   `wiki collect voice` manually.

Alternative paths (no engine change required):

- FluidVoice: same approach, point its export at `~/VoiceIntake`.
- macOS built-in dictation: paste into a `.txt` in the inbox.
- Hammerspoon snippet: capture clipboard → write timestamped file.

## Deferred (not in durchstich)

- **Audio-file ingestion** — pass `.m4a` / `.wav` through whisper.cpp /
  Parakeet ourselves. Doubles the value but doubles the surface; only
  worth it once the text-inbox path proves daily-use.
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
