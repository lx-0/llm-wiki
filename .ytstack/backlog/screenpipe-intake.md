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

## Capture setup — SHIPPED 2026-06-09 (operator machine)

The recording layer is live-tested on the operator's Mac. Reproducible elsewhere
(Sid / a third machine) by adjusting only **three machine-specific values**:
the Node/binary path, the audio-device names (`screenpipe audio list`), and
`$HOME`/username.

1. **Install CLI** (free MIT, no self-compile — Sid self-compiles only because he
   dev's on the source): `npm i -g screenpipe` → native binary lands at
   `…/node_modules/@screenpipe/cli-darwin-arm64/bin/screenpipe`.
2. **LaunchAgent** `~/Library/LaunchAgents/com.alex.screenpipe.plist`
   (KeepAlive + RunAtLoad, 24/7). Key choices, all verified against 0.4.12
   `record --help`:
   - References the **native binary path directly** (not the asdf shim / a shell
     wrapper) → no asdf/PATH dependency at boot **and** a clean TCC identity
     (the recording process is screenpipe itself, not vscode/Terminal).
   - `--language german` + `--audio-transcription-engine whisper-large-v3-turbo`
     — the default engine `parakeet` is English-centric and would mangle German.
     Fallback if 24/7 is too CPU/battery-hungry: `whisper-large-v3-turbo-quantized`.
   - `--audio-device "MacBook Pro Microphone (input)"` + `"System Audio (output)"`
     (mic + meeting counterpart), `--disable-telemetry`,
     `--data-dir /Users/alex/.screenpipe`.
   - `EnvironmentVariables.PATH` includes `/opt/homebrew/bin` — the minimal
     LaunchAgent PATH has no Homebrew, and screenpipe needs system `ffmpeg`
     (it bundles none) for audio transcription. Silent-crash trap if omitted.
3. **TCC permissions** must be granted to the screenpipe binary *as its own
   process* — run it once interactively from **Terminal.app** (not VS Code, or
   the grant attaches to vscode) so macOS prompts for Screen Recording + Mic
   against screenpipe, then `launchctl load -w`.

**Verified today (REGEL #1):** native binary runs (0.4.12, Mach-O arm64),
18s screen-only smoke capture wrote `db.sqlite` with 10 frames across 3 monitors,
plist passes `plutil -lint`. **Not yet verified:** the standalone 24/7 agent run
+ German whisper transcription (both gated on the operator's TCC grant + first
model download).

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
