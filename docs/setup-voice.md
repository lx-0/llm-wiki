# Voice intake setup

The voice collector (`scripts/collectors/voice.py`) ingests dictated text
from a local inbox directory. It accepts any tool that writes `.txt` or
`.md` files into that directory — OpenWhispr is the default
recommendation, but FluidVoice, macOS built-in dictation, and Hammerspoon
snippets all work without engine changes. Tool-landscape rationale lives
in [`.ytstack/backlog/voice-intake.md`](../.ytstack/backlog/voice-intake.md).

## 1. Pick an inbox path

```bash
mkdir -p ~/VoiceIntake
```

Any local path works. iCloud Drive / Syncthing paths also work if you
want voice notes mirrored across machines (untested, but the collector
only cares that the path exists).

## 2. Wire it in `config.yaml`

In `<vault>/.wiki/config.yaml`:

```yaml
personal:
  voice_inbox: "~/VoiceIntake"   # absolute or `~`-expanded
```

The piggyback is on by default with a 1 h cooldown. To disable
auto-runs (keep operator-invoked only):

```yaml
piggybacks:
  voice:
    enabled: false
```

## 3. Point a dictation tool at the inbox

### OpenWhispr (recommended)

1. Install from <https://github.com/OpenWhispr/openwhispr>.
2. In OpenWhispr settings, set "Save transcript to file" target to
   `~/VoiceIntake/voice-$(date +%s).txt`. (Pattern: any filename ending in
   `.txt` or `.md`; non-dot files in the inbox root are picked up on the
   next collector run.)
3. Pick a model: Parakeet for offline-first, Whisper for accuracy, any
   BYOK cloud for fastest turnaround.

### FluidVoice (macOS-native, pure-local)

Same recipe — set FluidVoice's export target to `~/VoiceIntake/`. License
is GPLv3 instead of MIT.

### macOS built-in dictation

Trigger dictation (default: hold the Fn key), paste into a new
`~/VoiceIntake/note.txt`, save. The collector picks it up.

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
