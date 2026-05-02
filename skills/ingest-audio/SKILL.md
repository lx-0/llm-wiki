---
name: ingest-audio
version: 1.0.0
description: |
  Ingest audio files into an Obsidian vault. Transcribes audio (Whisper API or local
  whisper.cpp), categorises content with an LLM, creates a vault note with frontmatter,
  embedded audio player, transcript, and suggested filing location.
  Use when: new audio files appear, user drops audio, or asks to transcribe.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

# Audio Ingest Pipeline

## Overview

Processes audio files (`.mp3`, `.m4a`, `.wav`, `.ogg`, `.webm`) and turns them into structured Obsidian vault notes with transcription, metadata, and categorisation.

## Configuration

```bash
VAULT="${VAULT_ROOT:?VAULT_ROOT must be set to your Obsidian vault path}"
INBOX="${INBOX_DIR:-Inbox}"        # folder name relative to VAULT
```

## Pipeline

### Step 1 — find audio files

Typical locations:
- Vault root (dropped files)
- `<inbox>/`
- `_attachments/` folders
- User-specified path

```bash
# Audio files in vault that don't yet have a companion .md note
find "$VAULT" -maxdepth 3 \
  \( -name "*.mp3" -o -name "*.m4a" -o -name "*.wav" -o -name "*.ogg" -o -name "*.webm" \) \
  -not -path "*/.obsidian/*" 2>/dev/null
```

### Step 2 — transcribe (fallback chain)

Try each in order; use the first that works.

#### Fallback 1 — OpenAI Whisper API (preferred — fast, high quality)

Requires `OPENAI_API_KEY`. Probe first:

```bash
[ -n "$OPENAI_API_KEY" ] && echo "API key present" || echo "no key"
```

If available:

```bash
curl -s https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F file="@$AUDIO_FILE" \
  -F model="whisper-1" \
  -F response_format="text"
```

#### Fallback 2 — local whisper / whisper.cpp (free, offline)

```bash
which whisper 2>/dev/null || which whisper.cpp 2>/dev/null || which whisper-cpp 2>/dev/null
```

If available:

```bash
whisper "$AUDIO_FILE" --model base --language auto --output_format txt --output_dir /tmp/
```

If not installed, suggest:

```bash
# macOS
brew install whisper-cpp
# or via pip
pip install openai-whisper
```

#### Fallback 3 — no transcription available

If neither works:
1. Create the note with a `> TODO: transcribe` placeholder.
2. Tell the user which install options exist (above).
3. Categorise based on filename, file metadata, and surrounding context.

### Step 3 — categorise

Analyse the transcript to determine:

1. **`type`** — what kind of content?
   - `note` — general thoughts, voice memo
   - `idea` — creative idea, product concept
   - `meeting` — meeting recording, discussion
   - `briefing` — instructions or task description

2. **`tags`** — relevant topics inferred from the transcript.

3. **target folder** — where it should live. Discover the user's top-level areas with `ls -d "$VAULT"/*/ | grep -v _attachments` and match content to one of them. Within the area, pick a PARA level (`Projects/`, `Areas/`, `Resources/`, `Archives/`). Default fallback: `<INBOX>/` if unclear.

4. **title** — generate a descriptive title from the transcript (1–8 words).

### Step 4 — create vault note

Move the audio file to `_attachments/` in the target folder; create the companion note:

```markdown
---
type: {{type}}
tags: [{{tags}}]
agent: true
status: review
source: audio
date: {{date_from_filename_or_today}}
---

# {{generated_title}}

> Audio file transcribed and categorised by the ingest-audio pipeline.

## Audio

![[{{audio_filename}}]]

## Details

- **Created:** {{date}}
- **Duration:** {{duration if available}}
- **Source:** {{source info — e.g. Voice Memo, ElevenLabs, meeting recording}}
- **Language:** {{detected language}}

## Transcript

{{full_transcript}}

## Summary

{{1–3 sentence summary of content}}
```

### Step 5 — file the note

- Create the note in `$INBOX/` with `status: review`.
- Move the audio file into `<target_folder>/_attachments/`.
- `AskUserQuestion` to confirm the suggested categorisation:
  - Suggested title
  - Suggested folder
  - Suggested type and tags
  - Allow override before finalising.

## Rules

- **Always `status: review`** — nothing files without user approval.
- **Always `agent: true`** — mark as agent-generated.
- **Preserve originals** — never delete audio; only move.
- **Match note language to transcript language** — auto-detect, don't translate unless asked.
- **Batch support** — multiple files: process each, present all for review at once.
- **Frontmatter follows vault conventions** — read `<vault>/AGENTS.md` or `<vault>/CLAUDE.md` first if present.

## Example invocations

```text
"transcribe the audio file in my inbox"
"ingest all audio files"
"/ingest-audio"
"transkribiere die neue sprachmemo"
```
