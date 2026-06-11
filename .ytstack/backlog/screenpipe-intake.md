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

- **SQLite schema — PROBED 2026-06-10 against the live DB** (v0.4.12, schema
  migration `20260603120000`; collector must record the `_sqlx_migrations`
  version it was built against). Key findings, all verified with real rows:
  - **Multi-screen artifact mitigation is built in:** `frames` carries
    `device_name` (= `monitor_N`), `focused` (bool), `app_name`, `window_name`,
    `browser_url`, `capture_trigger` (click/visual_change/window_focus) and
    `content_hash`/`simhash`. The collector reasons over focused+window, never
    raw frame order — prior-art trap #2 is solved at the source.
  - **Author attribution is a clean boolean:** `audio_transcriptions.
    is_input_device` (1 = mic = operator voice, 0 = System Audio = counterpart)
    + `device`, `start_time`/`end_time`. Maps 1:1 onto M009 `author:`.
  - **Diarization is live:** `speakers` table with 512-dim centroids +
    `hallucination` flag; `speaker_id` populated on ~100 % of transcripts
    (5 unnamed speakers after half a day). Naming/merging is open — possible
    tie-in with `wiki dedup`'s entity-merge.
  - **Watermark + retention hooks exist:** `audio_chunks.transcription_status`
    (pending/transcribed/silent/failed) and `evicted_at`; FTS5 mirrors
    (`*_fts`) for search.
  - **Built-in meeting detector:** `meetings` + `meeting_transcript_segments`
    (meeting_app, attendees, speaker_name, per-segment provider). 0 rows so far
    on this install — observe over real meetings; overlaps Jamie's territory
    (Jamie stays the meeting substrate per DECISIONS 2026-05-13; screenpipe
    meetings are at most a fallback signal).
  - **⚠️ `ui_events` is a keystroke log:** `event_type='text'` rows carry
    `text_content` = literally typed text (passwords/DMs land here). HARD RULE
    for the collector: **never ingest `ui_events.text_content`** — app/window
    switch events at most, for episode segmentation.
  - Volume reality: ~670 MB per ~4 h active use ≈ 3–4 GB/day — far above the
    docs' 5–10 GB/month (confirmed end-of-day: 1.1 GB / ~7 h). Retention via
    `screenpipe db` cleanup / `evicted_at` must be part of the operating
    posture, not an afterthought.

  **Day-1 longitudinal observations (2026-06-10, full working day):**
  - **`speaker_id` is a raw cluster, NOT a person identity.** Diarization went
    5 → 41 speakers in one day (mostly tiny fragments). The collector must
    treat speaker ids as merge candidates, never as entities — naming/merging
    is operator-side, natural tie-in with `wiki dedup`'s confirm-merge flow.
  - **`silent` status is the ingest cut.** A quiet afternoon produced 1276
    `silent` vs 313 `transcribed` chunks; transcription is voice-gated by
    design, with a self-healing reconciliation pass (`transcribed N orphaned
    chunks`). Collector filters on `transcription_status='transcribed'` —
    no transcript-content heuristics needed to skip silence.
  - **Not every frame has OCR.** Only ~38 % of frames had `ocr_text` rows
    (event-driven capture + a noisy upstream `frame_linker: stale entries
    expired without pairing` WARN, ~2.5 k evicted pairings/day, `failed=0`).
    Collector must LEFT-JOIN frames→ocr, never assume pairing; the WARN spam
    is a known upstream wart, not a local misconfig.
  - **Built-in meeting detector found 0 meetings** despite a real call
    (~13:03) — detection is meeting-app-keyed, a plain call doesn't register.
    Reinforces: Jamie stays the meeting substrate; screenpipe `meetings` is
    opportunistic extra signal at best.

  **Day-2 observations (2026-06-11/12):**
  - **🐛 Upstream bug: System-Audio stream dies on sleep/wake.** After the
    first overnight sleep, the unlock handler rebuilds ONLY the mic stream
    (`rebuilding stream for MacBook Pro Microphone (input)` — no System-Audio
    counterpart in the log); the output stream stays a zombie. Evidence: last
    System-Audio chunk 06-11 00:25, mic uninterrupted through 06-12; a full
    lost capture day for the call/meeting counterpart. Recovery:
    `launchctl kickstart -k gui/$UID/com.alex.screenpipe` (verified 06-12:
    both devices restart). **Operating posture needs a freshness check** —
    alert when `max(timestamp)` of System-Audio chunks lags mic by hours while
    the service is up. Route the bug to Sid (he devs on screenpipe source) or
    file upstream.
  - **Mic channel = room audio, not operator speech.** A TV documentary
    playing in the room was transcribed in full as `is_input_device=1`
    (screen showed only Code/webmail at the time — external source, not Mac
    playback). `is_input_device` only says which capture path; author
    attribution additionally needs diarization (and the speaker clusters
    fragment hard: 41 → 120 in day 2). M009 `author:` mapping must be
    mic ∧ diarization-consistent, never mic alone.
  - Service robustness otherwise good: one uninterrupted process across
    2 days incl. multiple sleep/lock cycles, RSS stable ~370 MB; OCR pairing
    ratio rose to ~47 %; disk ~2 GB/day averaged incl. idle night.
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

### Prior art — Alex×Sid strategy talks 2026-05-08 (compiled in the operator wiki)

Screenpipe integration was discussed at length before this backlog existed — in
the **Yesterday product context**, compiled into the operator's wiki from the
Jamie transcripts (`raw/transcripts/jamie/2026-05-08--alex-x-sid-{1,2}-3--*.md`).
Wiki articles: `concepts/screenpipe-automation-screening-service` (planned
*customer*-facing automation-audit service — adjacent product, NOT this
collector), `concepts/feature-extraction-multi-channel-correlation`,
`concepts/screenpipe-multi-screen-artifact-bias`,
`concepts/mobile-tracking-gap-agentic-automation`. Three of those learnings are
load-bearing for the collector design:

1. **Features over raw frames** (Sid's data-science framing, explicitly brought
   into the LLM-wiki discussion). Raw screenpipe rows are not an analysis
   substrate — extract computed features first (his Claude run: Days-Since-
   Commitment, External Visibility 88 %, Manager- vs Creator-days). For the
   collector this strengthens the source-only/daily-rollup posture and suggests
   the daily rollup should carry *derived metrics* (app-time breakdown,
   meeting/focus blocks), not OCR dumps. Cross-channel timestamp-join
   (screenpipe + calendar + email + jamie) is exactly llm-wiki's substrate set —
   the dream-cycle is the natural consumer.
2. **Multi-screen capture artifact** — known LLM trap. With N monitors
   screenpipe stores N frames per tick; a naive time-sorted frame sequence made
   Claude hallucinate "thousands of app switches per day" in Sid's analysis.
   Collector/prompt must correlate by window-title/monitor-id and carry
   confidence fields, never reason over raw frame order. (Engine-side mirror of
   `feedback_audit_premise_before_designing`.)
3. **Mobile blindspot is structural.** ≥30 % of a mobile-heavy operator's
   productive time never touches the laptop (calls, WhatsApp, podcasts-as-work).
   Screenpipe covers the desktop axis only — document the coverage boundary in
   the persona framing; don't let downstream synthesis read absence-of-frames as
   idleness.

### Prior art #2 — Sid's production sp-skills (reviewed 2026-06-10)

Sid shared the three agent-skills he runs daily on his screenpipe capture
(sp-live / sp-protokoll / sp-coaching). Classification: **consumer/synthesis
layer, not producers** — in our terms they map to `wiki query` / compile /
dream-cycle, done agentically on-demand instead of by a pipeline. Not worth
porting wholesale, but they encode battle-tested answers to design questions our
collector still has open (full technical extraction preserved in project memory
`project_screenpipe_sid_skills_extraction`; the downloaded skill files
themselves are deleted):

1. **Episodes are the unit of ingest.** Continuous capture must be segmented
   into episodes (`id, date, start, end, title, kind, people, projects, status,
   summary`) before any distillation. Stable IDs derived from local-date +
   start-time + normalized context; derived artifacts win over raw slots on
   conflict; data gaps get an explicit `gap` status — **never hallucinated
   over**. This answers our "what is *one item* for compile?" question:
   episodes, not frames or 30s chunks.
2. **Whisper noise filter** (production-tuned): drop segments <15 chars,
   hallucination one-liners ("Okay.", "Danke.", "I'm sorry"), and stutter
   repetitions, before anything reaches a prompt.
3. **Device semantics = author attribution.** Mic/AirPods device = operator's
   own voice (or their side of a call); `System Audio` = the counterpart /
   played content. Maps directly onto the M009 `author:` axis.
4. **REST API is a viable read path** alongside direct SQLite:
   `GET :3030/search?content_type=audio|all|ocr&start_time=&end_time=&q=&app_name=&min_length=&limit=`
   (transcripts at `data[].content.{transcription,timestamp,device_name}`) and
   `GET :3030/activity-summary?start_time=&end_time=`. More schema-drift-stable
   than SQL, but requires the daemon up; SQLite works offline. Decide at
   collector-design time.
5. **Time-window heuristics** for episode bounding ("gerade" = 30–60 min,
   "Session" = 2–4 h, "der Tag" = 06:00–now) — useful defaults for episode
   segmentation and for any on-demand query verb.

## Next step

Not a milestone yet — operator is collecting test data first. When enough has
accumulated, run `office-hours` / `plan-milestone` on the collector with the
real DB schema in hand.

**User-facing docs deferred by decision (operator, 2026-06-10):** no
`docs/setup-screenpipe.md` until the collector ships — a setup doc in the
`docs/setup-*` family would present screenpipe as an active substrate
(FEATURES/cli linkage), which it is not yet. The collector milestone MUST
include `docs/setup-screenpipe.md` (capture recipe lives in this file, §"The
fix") + the FEATURES.md / cli.md listings in the same arc.
