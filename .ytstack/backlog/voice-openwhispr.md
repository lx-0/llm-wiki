# voice-openwhispr — OpenWhispr SQLite reader-kind for voice collector

OpenWhispr (macOS, v1.7.0) stores transcripts in `~/Library/Application Support/open-whispr/transcriptions.db` (SQLite), NOT as files in a folder. The current voice collector (`scripts/collectors/voice.py`) is folder-watch with flat `iterdir()` scan accepting only `.txt` / `.md` — incompatible with OpenWhispr's storage model. iOS-Shortcut transport works (writes `.md` directly into `voice_inbox`); OpenWhispr does not.

Per the v1.6.9 release notes OpenWhispr SHOULD support "export your notes to local Markdown files that mirror your folder structure" — operator searched v1.7.0 Settings UI on lxw 2026-05-16 and couldn't find the toggle. The setting may live in a folder-context menu, per-note Share menu, or sync-provider area not yet identified.

## Two paths forward (mutually exclusive)

### Path A — Operator finds the OpenWhispr export setting

Cleaner, no engine change. Configure OpenWhispr to write transcripts to `voice_inbox` (currently `~/Library/Mobile Documents/com~apple~CloudDocs/voice-inbox`) as flat `.md`/`.txt`. Voice collector then picks them up unchanged. **Open as of 2026-05-17.**

### Path B — Engine extension: `kind: openwhispr-sqlite` reader

Mirrors the jamie / gmeet / calendar account-bound multi-tenant pattern. ~80 LOC + test.

**Schema sketch:**

```yaml
personal.accounts.default.voice:
  kind: openwhispr-sqlite
  db_path: ~/Library/Application Support/open-whispr/transcriptions.db
  since: ""                # ISO date; empty = no backfill cap
  max_per_run: null        # null = inherit limits.voice_max_per_run (new default 100)
```

**Read logic:**
- Watermark: `last_seen_id` per-account in `state["voice"][<account>].last_seen_id`
- Query: `SELECT id, created_at, text, audio_duration_ms, provider, model FROM transcriptions WHERE id > ? AND status = 'completed' AND deleted_at IS NULL ORDER BY id LIMIT ?`
- Each row → `raw/voice/<YYYY-MM-DD>-<id>.md` with frontmatter `{captured_at, source: openwhispr, provider, model, duration_s, db_id}`
- No archive-move (DB is the source of truth + dedup mechanism via watermark; the audio file in `audio/<id>.webm` stays where it is — operator can rotate via OpenWhispr's own retention)

**Edge cases:**
- Concurrent OpenWhispr writes during read → use `BEGIN IMMEDIATE` or accept the small race (next run picks up)
- `deleted_at` set after we ingested → leave the `raw/voice/` copy (substrate is append-only by convention)
- `status != 'completed'` → skip (transcription failed; OpenWhispr will retry)

**Effort:** 1-2 sessions. Includes `kind` discriminator wiring in `_resolve_voice_accounts()`, test fixtures, doc updates in PROCESS.md + AGENTS.md + config.example.yaml.

## Don't do this

- **Bridge script** that polls the DB and dumps `.txt` into `voice_inbox`. Workaround-flavor, two moving parts where one would suffice, hard to make robust to OpenWhispr schema drift.
- **Symlink audio/ to voice_inbox.** Wrong format (`.webm`); collector skips silently.

## Triggers for reopening

- Path A: operator confirms they can or can't find the setting.
- Path B: operator wants automation without depending on OpenWhispr UI behavior across upgrades.

## References

- OpenWhispr OSS at github.com/OpenWhispr/openwhispr
- Release notes 1.6.9: github.com/OpenWhispr/openwhispr/releases/tag/v1.6.9
- Voice collector: `scripts/collectors/voice.py`
- Multi-tenant kind-dispatch pattern: jamie/gmeet/calendar in `scripts/core/config.py` `_resolve_*_accounts()` family
- DB schema (from live audit): `transcriptions` table cols `id, text, timestamp, created_at, raw_text, has_audio, audio_duration_ms, provider, model, status, error_message, error_code, client_transcription_id, cloud_id, sync_status, deleted_at`. Other tables present: `notes`, `folders`, `actions`, `contacts`, `calendar_events`, `agent_conversations`, `agent_messages`, `google_calendar_tokens`, `speaker_profiles`, `speaker_mappings`, `note_speaker_embeddings`.
