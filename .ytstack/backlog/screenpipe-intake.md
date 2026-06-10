---
title: Screenpipe intake collector
status: capture-setup-shipped (collector unbuilt)
captured: 2026-06-09
related: [[screenshots-intake]], [[voice-intake]], [[consumption-curiosity-axis]], [[meetily-intake]]
context: Operator + CEO (Sid) both running 24/7 screenpipe; collector is the open llm-wiki work
---

# Screenpipe intake

## Premise

[Screenpipe](https://github.com/screenpipe/screenpipe) is a 24/7 local
screen-+-audio recorder: MIT-licensed CLI captures every frame (OCR'd) and every
audio stream (whisper-transcribed) into a local SQLite DB. A future
`collectors/screenpipe.py` reads that DB directly and distills it into the
llm-wiki pipeline — a new substrate alongside email / jamie / gmeet / voice /
youtube / pictures / screenshots.

**Persona-axis value (per DECISIONS 2026-05-22 — intake = persona-coverage, not
signal-density):** 24/7 screen-memory is the *broadest* substrate yet. It covers
work *and* the non-work self (what the operator reads, watches, idly browses,
says out loud) in one stream — axes that work-substrate (mail/calendar/docs)
systematically misses. That breadth is also its central risk (below).

## Not Sid's overlay — capture-layer only

Sid (CEO) runs a full screenpipe **productivity overlay**: 13 custom pipes
(wow-analyzer, standup-update, day-recap…), 4 Cursor agent-skills (sp-live,
sp-protokoll, sp-coaching, sp-stop), a `user-screenpipe` MCP server, and a
nightly transcript export pushed to a GitHub repo (`Sidwach/screenpipe-exports`).

**For llm-wiki, none of that overlay is needed.** Our collector reads the SQLite
directly and the distillation happens in `compile.py`. Sid's pipes/export/Cursor
skills would *double* that work and are Cursor-/his-repo-specific. The nightly
Markdown export in particular is pointless for us: the collector reads the live
DB (WAL read-side works while screenpipe writes — `screenpipe search`/`export`
prove it), so a Markdown intermediate is a redundant second source of truth.

**Re the old rejection:** `rejected/meetily-intake.md` + DECISIONS 2026-05-13 set
screenpipe aside *for meetings* as "different category, desktop app paid". The
"paid" note was the Tauri desktop app — the **CLI capture layer is free MIT**
(`npx screenpipe` / `npm i -g screenpipe`). Meetings remain Jamie's job; this is
the broad screen-memory axis, not a meeting-notetaker.

## Capture setup — SHIPPED & VERIFIED 2026-06-10 (operator machine)

24/7 capture is live and end-to-end verified on the operator's Mac. Reproducible
elsewhere (Sid / a third machine) by adjusting only the **machine-specific
values**: the source binary path, the audio-device names (`screenpipe audio
list`), and `$HOME`/username.

### The load-bearing macOS gotcha — a bare CLI binary under launchd gets NO Mic/Screen

This cost the most time, so it's the headline. On macOS, TCC permissions
(Screen Recording, Microphone, Accessibility) attribute to the **launching GUI
process**, not to a bare CLI binary. Consequences observed:

- A LaunchAgent pointing straight at the npm binary → `microphone: waiting →
  timed out waiting for permissions`, KeepAlive respawns in a loop, **0 captured**.
- `screenpipe doctor` showed `mic ok` — but only because doctor ran inside the
  VS Code context, which had the grant. The launchd process is a *different* TCC
  identity and inherits nothing.
- Granting Mic via an interactive Terminal start binds the grant to **Terminal**,
  not to the binary → the launchd service still gets nothing.
- `screenpipe` never appears in System Settings → Microphone (Mic has no "+"
  button, and a bare binary can't register itself there).

This is exactly the problem the **paid signed desktop app** solves out of the box.

### The fix — wrap the binary in a signed .app bundle

1. **Install CLI** (free MIT, no self-compile): `npm i -g screenpipe` (v0.4.12)
   → native binary at `…/node_modules/@screenpipe/cli-darwin-arm64/bin/screenpipe`.
2. **Build `~/Applications/Screenpipe.app`:**
   - `Contents/MacOS/screenpipe` = a **copy** of the native binary (after
     `npm update -g screenpipe`, re-copy + re-codesign).
   - `Contents/Info.plist` with `CFBundleIdentifier=com.alex.screenpipe`,
     `CFBundleExecutable=screenpipe`, `LSUIElement=true`, and crucially
     `NSMicrophoneUsageDescription` — the usage string is what makes macOS
     attribute the Mic prompt to **the bundle id**, which is a stable TCC subject.
   - `codesign --force --sign - --identifier com.alex.screenpipe Screenpipe.app`
     (ad-hoc is fine) + `lsregister -f Screenpipe.app`.
3. **LaunchAgent** `~/Library/LaunchAgents/com.alex.screenpipe.plist`
   (`KeepAlive` + `RunAtLoad`) → `ProgramArguments[0]` =
   `…/Screenpipe.app/Contents/MacOS/screenpipe`, then `record` with:
   - `--language german` + `--audio-transcription-engine whisper-large-v3-turbo`
     (default `parakeet` is English-centric; fallback `…-turbo-quantized` if 24/7
     is too CPU/battery-hungry).
   - `--audio-device "MacBook Pro Microphone (input)"` + `"System Audio (output)"`
     (own voice + meeting counterpart), `--disable-telemetry`,
     `--data-dir /Users/alex/.screenpipe`.
   - `EnvironmentVariables.PATH` includes `/opt/homebrew/bin` — minimal launchd
     PATH has no Homebrew, and screenpipe needs system `ffmpeg` (bundles none).
     Silent-crash trap if omitted.
4. **Grant TCC to the bundle once** (cannot be scripted — SIP):
   - **Screen & System Audio Recording** → "+" → `Screenpipe.app` → on.
   - **Accessibility** → "+" → `Screenpipe.app` → on (for UI-element capture).
   - **Microphone** → appears as `Screenpipe` once the bundle has requested it
     (start it once via `open Screenpipe.app --args record …`) → on.
   - Then `launchctl load -w …`. The launchd run inherits all three via the
     bundle id.

**Verified 2026-06-10 (REGEL #1), under the real launchd service (PPID 1):**
`permission monitor started screen=true mic=true accessibility=true`,
`VisionManager started with 1/1 monitor(s)`, recording on both mic + System Audio,
and growing data: frames 24, ocr_text 19, audio_chunks 11, **audio_transcriptions
10** with a correct **German** transcript from system audio. `db.sqlite` at
`~/.screenpipe/`.

## Collector design — OPEN

The actual llm-wiki feature. Unbuilt. Open questions before a milestone:

- **SQLite schema.** Confirmed a `frames` table exists (OCR/vision). Need to map
  the audio-transcription tables + how mic vs system-audio + speaker labels are
  stored. Live-probe the real DB before writing any parser (per
  `feedback_live_probe_before_parser` — don't trust docs/memory on schema).
- **What to ingest, and at what compile-role.** This is the load-bearing
  decision. Screenpipe produces ~5–10 GB/month and *enormous* OCR volume —
  ingesting raw frames as per-item `knowledge/` would bury the vault. Almost
  certainly `compile-role: source-only` + `daily/`-rollup aggregation (same
  posture as low-signal consumption sources), NOT per-frame articles. The
  audio-transcript side is higher-signal (what the operator actually said) and
  may warrant finer treatment than the OCR-frame side.
- **Privacy / PII.** 24/7 capture is the most sensitive substrate by far —
  passwords, DMs, banking, private screens all pass through. screenpipe has
  `--use-pii-removal` / `--ignored-windows` / `--ignored-urls` capture-side
  knobs; the collector additionally needs aggressive ingest-side filtering and a
  clear redaction story before anything reaches `knowledge/`.
- **Multi-tenant from day one** (per `feedback_account_adapters_multi_tenant`):
  `personal.accounts.<id>.screenpipe` with a `data_dir` per machine, since
  operator + Sid both run it.
- **Dedup vs screenshots-intake.** The existing screenshot collector already
  OCRs ad-hoc screenshots; screenpipe's continuous frames overlap. Decide whether
  screenpipe supersedes or complements it.

## Next step

Not a milestone yet — operator is collecting test data first. When enough has
accumulated, run `office-hours` / `plan-milestone` on the collector with the
real DB schema in hand.
