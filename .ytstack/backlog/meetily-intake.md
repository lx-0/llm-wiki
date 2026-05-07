# Meetily intake — concept

**Status:** Phase 1 (concept) — pending user review.
**Companion to:** `youtube-intake.md` (template for tier-based piggyback ingest)
**Related memory:** `project_meeting_intake_candidates.md`

## What

A `wiki ingest-meetily` subcommand that reads Meetily's local SQLite DB read-only and writes one markdown file per meeting into `<vault>/raw/transcripts/meetily/`. No re-recording, no separate audio pipeline — Meetily owns audio capture + transcription + LLM summarisation; the wiki engine only consumes its output.

Pattern is a thin parallel to `scan-youtube.py` but radically simpler (no LLM tiers, no network, no rate-limit handling — Meetily already did the work; we map rows → markdown).

## Why

- Three FOSS meeting-intake candidates were evaluated (Meetily / Screenpipe / Ghostpepper). Meetily won on installed-and-working basis (test summary already exists in DB at install time).
- Jamie was rejected (Pro-gated API + nothing local), Hyprnote/anarlog deprioritised (team focus shifted to commercial char.com).
- Meetings are a high-value first-party signal — action items, decisions, attendees — currently entirely missing from the wiki's substrate set.
- Meetily writes `summary_processes.result.markdown` already formatted with `**Summary**` / `**Key Decisions**` / `**Action Items**` table — wiki compile.py can consume this directly without re-summarisation.

## How

### Source: Meetily SQLite

Read-only query against `~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite` (configurable via `personal.meetily_db_path` for non-default installs / Linux ports / future schema versions).

Tables touched (read-only via `sqlite3 ... mode=ro`):

| Table | Used for |
|---|---|
| `meetings` | id, title, created_at, updated_at, folder_path |
| `summary_processes` | result (JSON `{markdown}`), status, processing_time, model used |
| `meeting_notes` | notes_markdown (user-typed notes if any) |
| `transcripts` | transcript text per chunk + audio_start_time + speaker (if diarized) |
| `transcript_chunks` | model name + chunk metadata for frontmatter |
| `_sqlx_migrations` | schema-version pin (fail-loud on unfamiliar version) |

### Output: one markdown per meeting

Path: `<vault>/raw/transcripts/meetily/<date>--<slug>--<short-id>.md`
Example: `2026-05-04--meeting-discussion-on-app-transcriptions--0e99900f.md`

Frontmatter (consistent with YouTube sidecar shape):

```yaml
type: transcript          # consumed by compile.py source-type dispatch
source: meetily
meeting_id: meeting-0e99900f-1ee2-4053-8677-aabf83629bb8
title: Meeting Discussion on App Transcriptions and Models
started_at: 2026-05-04T13:21:32+00:00
ended_at:   2026-05-04T13:33:18+00:00
duration_min: 12
folder_path: /Users/alex/Movies/meetily-recordings/Meeting 2026-05-04_15-21-32_2026-05-04_13-21
transcript_model: whisper-large-v3      # from transcript_chunks.model
transcript_chunks: 47
summary_status: completed
summary_model: gemma3                   # from summary_processes.metadata if available
speakers: [Alex, Sidney]                # nullable; only when diarization populated
ingested_at: 2026-05-04T13:35:00+00:00
input_source: cli                       # cli|piggyback
tags: [meeting, meetily]
tier: 2                                 # 0=metadata, 1=+summary, 2=+transcript
```

Body sections (in order, only emitted when source data present):

1. **Header line** — `_<duration_min> min · <speakers> · <date>_`
2. **Summary** — verbatim `summary_processes.result.markdown` (already formatted by Meetily's local LLM)
3. **User notes** — `meeting_notes.notes_markdown` if non-empty, in a `> [!note]` callout
4. **Transcript** — concatenated chunks, ordered by `audio_start_time`, formatted as:
   ```
   `[mm:ss]` **<speaker>** — <text>
   ```
   `[mm:ss]` anchor matches youtube-intake convention so compile.py + lint stay uniform.

### CLI

```
wiki ingest-meetily [--tier {0,1,2}] [--limit N] [--since DATE]
                    [--db PATH] [--meeting-id ID] [--dry-run] [--no-skip]
```

- `--tier 0` = frontmatter only (metadata smoke-test)
- `--tier 1` = + summary block (Meetily LLM output)
- `--tier 2` = + full transcript (default)
- `--since 2026-05-01` = ingest only meetings whose `created_at >= since`
- `--meeting-id <id>` = single-meeting mode for debugging
- `--db PATH` = override `personal.meetily_db_path`
- `--dry-run` / `--no-skip` = analogous to scan-youtube.py

### Piggyback integration

```yaml
piggybacks:
  scan_meetily:
    enabled: true
    cooldown_hours: 6              # tighter than youtube — meetings are time-sensitive
    max_per_run: 20
```

Ran from `flush.py` after `compile_after_hour`. Skip-existing keyed on `meeting_id` (UUIDv-style stable id from Meetily, robust to title edits).

## Edge cases

| Case | Behavior |
|---|---|
| DB locked (Meetily live-recording) | Open via SQLite URI `file:...?mode=ro&immutable=0` — WAL mode is concurrent-read-safe. |
| Empty `summary_processes.result` (still summarising or failed) | Write tier-0 file with `summary_status: pending` in frontmatter; piggyback re-tries on next run since meeting_id stays the same. **Add `--no-skip` semantics: re-write if `summary_status: pending`.** |
| No `summary_processes` row at all (very fresh recording) | Skip; cooldown means we'll catch it next run. Log at INFO. |
| Empty `transcripts` table for a meeting | Tier-2 emits "(no transcript chunks captured)" placeholder — meeting still has summary value. |
| `meetings.folder_path` NULL | Frontmatter omits the field; no error. |
| Schema drift (Meetily upgrade renames columns) | `_sqlx_migrations` table queried at startup; if max version > known-good (pinned in script constant), warn + abort with explicit upgrade prompt. Fail-loud per CLAUDE.md "Sub-Agent-Output verifizieren". |
| Same meeting ingested twice | meeting_id-keyed skip-existing; idempotent. `--no-skip` re-renders (e.g. after summary completes). |
| Transcripts > compile.py budget | No special handling — compile.py already chunks long sources. |
| Speakers column empty | `speakers:` key omitted from frontmatter. Body uses `**unknown**` per chunk. |
| Multiple meetings with same slug-prefix | meeting_id short-prefix in filename guarantees uniqueness. |
| Meetily not installed (no DB file) | CLI exits 0 with "no Meetily DB at <path> — skipping" (not an error — many installs won't have it). Piggyback no-ops. |
| `personal.meetily_db_path` unset on non-macOS | Falls back to platform default (`~/.local/share/meetily/...` on Linux when Meetily ships there; nothing today, so script logs + skips). |

## What this concept does NOT include

- No re-summarisation: we trust Meetily's LLM output. compile.py downstream synthesizes the wiki article; we don't double-LLM the raw.
- No audio file copying / transcoding: `folder_path` is recorded for provenance only. Audio stays in `~/Movies/meetily-recordings/` owned by Meetily.
- No real-time hook: ingest runs on schedule (CLI or piggyback), not on Meetily-finished-recording event. Hook-based variant deferred to a follow-up.
- No Meetily Pro features (cloud sync, license-keyed transcripts) — pure community-edition path. License table is read for status display only, never required.
- No two-way sync (writing wiki notes back into Meetily's `meeting_notes`). One-way: Meetily → wiki.

## Files affected (Phase 2 will verify exact line numbers)

| File | Change |
|---|---|
| `scripts/scan-meetily.py` | NEW — analog `scan-youtube.py`, ~250 LOC |
| `wiki` (CLI dispatcher) | Add `cmd_ingest_meetily` + dispatch case + help block |
| `scripts/wiki_config.py` | Add `Limits.meetily_*` fields, extend `Personal.meetily_db_path`, add `scan_meetily` to `_default_piggybacks()` |
| `config.example.yaml` | Add `piggybacks.scan_meetily` + `personal.meetily_db_path` example |
| `scripts/flush.py` | Wire `scan_meetily` into PIGGYBACK_TASKS dispatch (if pattern requires registration there) |
| `AGENTS.md` | Add row to "raw/ substrates" table; add `meetily` to source-type list |
| `docs/PROCESS.md` | Add ingest-pipeline section with mermaid + edge-case table |
| `README.md` | One-line CLI example near the other ingest examples |
| `.ytstack/KNOWLEDGE.md` | Hard-won: SQLite WAL read-while-locked pattern (only if it fights us) |
| `docs/architecture.excalidraw` | Add Meetily node + arrow into raw/transcripts/ |
| `docs/vault-tour.excalidraw` | Add `raw/transcripts/meetily/` subfolder to the vault tree |

## Open questions for review

1. **Path placement:** `raw/transcripts/meetily/` (uses existing `RAW_TRANSCRIPTS_DIR` constant + sub-bucket) vs `raw/notes/meetily/` (mirrors YouTube's `raw/notes/youtube/` pattern). Concept proposes `raw/transcripts/meetily/` because the existing constant fits and meetings ARE transcripts. **Confirm preference.**

2. **Tier model:** Three tiers (metadata / +summary / +transcript) feels overengineered for a single-source ingest. Could collapse to one default-everything mode and add `--summary-only` / `--no-transcript` flags if needed. **Confirm preference.**

3. **Speaker handling when diarization is absent:** Concept suggests `**unknown**` per chunk. Alternative: drop speaker prefix entirely when uniformly absent so transcripts don't get noisy. **Confirm preference.**

4. **Cooldown:** 6h proposed (vs youtube's 24h) on the theory that meetings are time-sensitive (capture today's standup before the daily-log gets compiled). 24h works fine if you'd rather not over-trigger. **Confirm preference.**

5. **`--since` default:** Concept defaults `--since` to "no filter" (full re-scan, skip-existing handles dedup). Alternative: default to 30 days back so first-run on a 1000-meeting DB doesn't churn. **Confirm preference.**
