# Voice intake setup

The voice collector (`scripts/collectors/voice.py`) ingests dictated text
from an inbox directory. It accepts any tool that writes `.txt` or
`.md` files into that directory — local Mac apps (OpenWhispr, FluidVoice,
macOS built-in dictation, Hammerspoon snippets) and **iOS Shortcuts on
iPhone via an iCloud-Drive-synced inbox** both work without engine
changes. Tool-landscape rationale lives in
[`.ytstack/backlog/voice-intake.md`](../.ytstack/backlog/voice-intake.md).

## 1. Pick an inbox path

For **mobile-first capture** (recommended — iPhone is the daily-driver
surface for most operators), put the inbox under iCloud Drive so iOS
Shortcuts can write directly:

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/VoiceIntake
```

On iOS, this folder shows up in the Files app as `iCloud Drive →
VoiceIntake`.

For **Mac-only capture**, any local path works:

```bash
mkdir -p ~/VoiceIntake
```

The collector is path-agnostic — pick once, wire once, done.

## 2. Wire it in `config.yaml`

In `<vault>/.wiki/config.yaml`:

```yaml
personal:
  voice_inbox: "~/Library/Mobile Documents/com~apple~CloudDocs/VoiceIntake"
  # or: voice_inbox: "~/VoiceIntake"
```

The piggyback is on by default with a 1 h cooldown. To disable auto-runs
(keep operator-invoked only):

```yaml
piggybacks:
  voice:
    enabled: false
```

## 3. Point a dictation tool at the inbox

### iOS Shortcut — Action Button → dictate → save (mobile primary)

Apple's on-device dictation is good enough for 30 s–2 min captures
("remind me to X", "thought: …", "todo: …") and runs offline on
iPhone 12 or newer. The Shortcut writes a `.txt` straight into the
iCloud-Drive inbox; iCloud syncs it to the Mac within ~30 s–2 min;
the collector picks it up on the next piggyback or `wiki collect voice`.

**Build it once on iPhone (Shortcuts app → + → New Shortcut):**

1. **Action 1 — Dictate Text**
   - Language: your spoken language
   - Stop Listening: *After Long Pause* (lets you breathe mid-sentence
     without ending the capture)
2. **Action 2 — Get Current Date**
   - Use as Filename
   - Format: `Custom`, pattern: `yyyy-MM-dd-HHmmss`
3. **Action 3 — Save File**
   - Content: *Dictated Text* (from Action 1)
   - Service: *iCloud Drive*
   - Destination: `VoiceIntake/voice-{Formatted Date}.txt`
   - Ask Where to Save: **Off**
   - Overwrite If File Exists: **Off** (the timestamp makes collisions
     impossible anyway)

Name the Shortcut `Capture Voice Note`.

**Bind it to a hardware trigger:**

- Settings → Action Button → *Shortcut* → *Capture Voice Note*
  (iPhone 15 Pro and later)
- *or* Settings → Accessibility → Touch → Back Tap → *Double Tap* →
  *Capture Voice Note* (works on any iPhone 8+)
- *or* Hey Siri → "Capture Voice Note" (no hardware setup needed)

**Limitations to know:**

- Dictation hard-cuts after ~60 s of silence regardless of "Stop
  Listening" setting. For long-form (commute / walks), use Voice Memos
  + a Mac-side whisper watcher — that path is in
  [`.ytstack/backlog/voice-intake.md`](../.ytstack/backlog/voice-intake.md)
  under "Deferred".
- Apple dictation quality ≈ Whisper-small. Fine for personal notes;
  proper-noun-heavy domains (medical / legal / technical jargon) may
  want a Whisper-based app instead — see Aiko below.

### Aiko (iOS, free, MIT-spirit) — Whisper on-device for iPhone

If you want better transcription quality than Apple's native dictation,
[Aiko by Sindre Sorhus](https://sindresorhus.com/aiko) runs Whisper
locally on iPhone, free, no subscription. Exports land in the Files app
under `Aiko/`. To bridge into our inbox:

1. In Aiko: record + transcribe + tap *Export Text*.
2. Pick *Save to Files* → *iCloud Drive* → *VoiceIntake*.

Or wrap Aiko's *Share* action in a one-step Shortcut that hard-codes
the destination, so each note is one tap to file.

### OpenWhispr (Mac, recommended for desk capture)

1. Install from <https://github.com/OpenWhispr/openwhispr>.
2. In OpenWhispr settings, set "Save transcript to file" target to
   `~/VoiceIntake/voice-$(date +%s).txt` (or the iCloud path if you
   pointed `voice_inbox` there). Pattern: any filename ending in `.txt`
   or `.md`; non-dot files in the inbox root are picked up on the next
   collector run.
3. Pick a model: Parakeet for offline-first, Whisper for accuracy, any
   BYOK cloud for fastest turnaround.

### FluidVoice (macOS-native, pure-local)

Same recipe — set FluidVoice's export target to your `voice_inbox`.
License is GPLv3 instead of MIT.

### macOS built-in dictation

Trigger dictation (default: hold the Fn key), paste into a new `.txt`
in `voice_inbox`, save. The collector picks it up.

### Hammerspoon snippet (any clipboard text)

```lua
hs.hotkey.bind({"cmd", "shift"}, "v", function()
  local txt = hs.pasteboard.getContents()
  if not txt or txt == "" then return end
  local fname = os.date("~/VoiceIntake/clip-%Y%m%d-%H%M%S.txt")
  local f = io.open(os.getenv("HOME") .. fname:gsub("^~", ""), "w")
  f:write(txt); f:close()
  hs.alert.show("voice inbox: " .. fname:match("[^/]+$"))
end)
```

## 4. Run it

Operator-invoked:

```bash
wiki collect voice --dry-run     # show what would happen
wiki collect voice               # ingest + archive
```

Piggyback (auto, every 1 h after `compile_after_hour`): nothing to do.
Output lands in `<vault>/raw/voice/voice-YYYY-MM-DD-HHMM-<slug>.md` and
the source files are moved into `<voice_inbox>/.processed/` so re-runs
don't double-ingest.

## What the output looks like

```markdown
---
type: voice-note
origin: voice-intake
captured_at: 2026-05-15T20:43:12+02:00
source: voice-1747341792.txt
tags: [voice]
---

Erste Notiz über Voice intake — der collector zieht das hier in raw/voice/.
```

The compile pass (`wiki compile`) picks these up from `raw/voice/` like
any other substrate; no separate prompt is needed in the durchstich.

## Troubleshooting

- **iPhone wrote the file but Mac doesn't see it.** iCloud sync latency
  is usually 30 s–2 min. Open the Files app on iPhone and confirm the
  file exists; if it shows a cloud icon, force sync by tapping it. On
  Mac: `brctl download "~/Library/Mobile Documents/com~apple~CloudDocs/VoiceIntake/"`
  triggers eager download.
- **Shortcut runs but writes nothing.** First run prompts for
  permission to access iCloud Drive — accept it. After that, runs are
  silent unless you toggle *Show When Run* in the Shortcut header.
- **`wiki collect voice` says "not found".** The path in `voice_inbox`
  must already exist on disk. iCloud Drive folders are created lazily;
  drop one file via the Files app first, then re-run.
