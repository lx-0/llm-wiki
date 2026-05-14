# gmeet collector — Google Meet / Gemini transcripts as a substrate

**Priority:** P2 — new substrate, not a live bug. Operator already produces the
substrate (the "Meet Recordings" Drive folder fills up with Gemini transcripts);
nothing pulls it into the vault yet.

**Origin:** 2026-05-14, concept phase (llm-wiki-change skill). Scope = the
Gemini-generated transcription / notes Docs, **not** video processing.
**Drive-only wedge** — the Meet REST API enrichment was dropped after research
(2026-05-14) exposed three constraints: `conferenceRecords.list` is
organizer-only (misses attended-not-hosted meetings), records expire 30 days
after the conference, and transcript-entry speakers are resource names needing
extra participant-resolution calls. The Drive-Doc export is already
speaker-diarized and has none of those limits. See "Deferred" below.

## What

New registered Collector `scripts/collectors/gmeet.py` — structurally a near-copy
of `collectors/jamie.py` (the existing meeting-substrate precedent).

- `SPEC.name = "gmeet"`, output `raw/transcripts/gmeet/`, `piggyback_default=True`,
  `piggyback_cooldown_hours=6` (meetings time-sensitive — mirror jamie),
  `supports_incremental=True`, `supports_account_loop=False`.
- New `GmeetConfig` dataclass + `CONFIG.personal.gmeet` block — flat single-tenant,
  mirror `JamieConfig`.
- New `CONFIG.piggybacks.gmeet` entry + `_default_piggybacks()` row.
- New `wiki gmeet-auth <account-id>` CLI bootstrap — mirror `wiki gmail-auth`.
- New limits: `gmeet_request_timeout_s`, `gmeet_max_per_run`.
- State file `state/gmeet-state.json` carrying `last_seen_ts` (ISO 8601).
- One Registry wiring line: `from . import gmeet` in `collectors/__init__.py`.

## Why

Google Meet + Gemini ("Take notes with Gemini" / transcription) is a live meeting
substrate the operator already generates — every recorded Meet drops Gemini Docs
into the Drive "Meet Recordings" folder. Today that knowledge is trapped in Drive.
`jamie.py` covers Jamie-recorded meetings; `gmeet.py` covers Meet-native
Gemini-recorded ones. Two notetakers, two collectors, one `raw/transcripts/`
substrate. compile.py distills both the same way.

## How it integrates

**Auth — reuse the existing Google OAuth infrastructure.**
`google-auth` + `google-auth-oauthlib` are already deps. `adapters/mailbox/gmail.py`
already does the full OAuth dance: client secret at `<vault>/.claude/*-oauth-client.json`,
token cache under `state/`, bootstrap via `wiki gmail-auth`. gmeet copies the
pattern: `gmeet_auth_bootstrap()` → `wiki gmeet-auth <id>`, token cache
`state/gmeet-token-<account-id>.json`. Scope:
`https://www.googleapis.com/auth/drive.meet.readonly` — the dedicated narrow
scope for files created/edited by Google Meet. Both `files.list` (find the
Docs) and `files.export` (download them) fall under it.

**Harvest — Drive API.**
`files.list` with `q="'<folder-id>' in parents and mimeType='application/vnd.google-apps.document' and trashed=false"`.
Folder id from `CONFIG.personal.gmeet.drive_folder_id`; if empty, attempt
auto-resolve by name ("Meet Recordings", configurable) and fail with a clear
"set drive_folder_id" hint if the narrow scope blocks the name search. Meet
drops up to two Docs per meeting — "<title> - Notes by Gemini" (AI summary +
action items) and "<title> - Transcript" (already speaker-diarized). For each
Doc → `files.export(mimeType='text/markdown')` (officially supported for Google
Docs), `text/plain` fallback. 10 MB export cap per file. Group Docs by meeting
via shared title-stem.

**Render — one `.md` per meeting** → `raw/transcripts/gmeet/<date>--<slug>--<short-id>.md`.
Frontmatter mirrors jamie: `type: transcript`, `source: gmeet`, `meeting_id`
(Drive-derived short id), `title`, `started_at` (Doc `createdTime`),
`duration_min` (omitted — not in Drive metadata), `tags: [gmeet, meeting]`,
`drive_doc_ids`, `ingested_at`, `input_source`, `account_id`. Body: `## Summary`
(from the Notes-by-Gemini Doc export), `## Transcript` (the Transcript Doc export
— already `Speaker: text` diarized). `_render_markdown` adapts jamie's structure.

**Incremental + skip-existing.** `state/gmeet-state.json` `last_seen_ts`; highest
`started_at` of a successful run becomes the new watermark. Skip-existing keyed on
the short-id in the filename — same mechanism as jamie.

**flush.py / Registry — zero changes.** Registry auto-discovers via `@register`;
the piggyback auto-spawns through `collectors/cli.py gmeet`. Only `__init__.py`
gets the import line.

## Edge cases / failure modes

- **OAuth not bootstrapped** → no token cache → `is_configured()` False → piggyback
  silently skipped, CLI prints "not configured — run wiki gmeet-auth". Graceful-agnostic,
  same contract as jamie's unset `api_key_env`.
- **Folder auto-resolve blocked by narrow scope** → `files.list` name-search may
  not be permitted under `drive.meet.readonly`. On failure, log a clear hint to
  set `CONFIG.personal.gmeet.drive_folder_id` explicitly (the operator copies it
  from the folder URL once).
- **Transcription was off** → only a `.mp4` exists, no Docs → `mimeType=document`
  filter skips the meeting naturally.
- **Recordings (`.mp4`) are out of scope** — not the substrate, not downloaded, not
  vision-processed. The Gemini transcription/notes Doc *is* the knowledge.
- **Doc grouping ambiguity** — two meetings, same day, same title → Drive file-id
  short-id disambiguates. If a Notes Doc and Transcript Doc can't be paired, emit
  each rather than dropping content.
- **Markdown export unsupported for old Docs** → `text/plain` fallback.
- **Token refresh failure / revoked consent** → log warning, return
  `RunResult(message="auth expired — re-run wiki gmeet-auth")`, no crash.
- **API rate limits** — Drive + Meet 429 → retry-once-with-backoff, mirror jamie's
  `_JamieClient._get` retry shape.
- **Cross-notetaker duplication** — a meeting recorded by both Jamie *and* Meet-Gemini
  lands in both `raw/transcripts/jamie/` and `raw/transcripts/gmeet/`. Acceptable;
  compile.py distills. Cross-notetaker dedup is out of scope (possible future item).

## Resolved decisions (Phase 2)

- **OAuth code sharing** — extract `scripts/core/google_oauth.py` as a shared
  helper; refactor `gmail.py` onto it; `gmeet.py` uses it too. (User decision.)
- **OAuth client-secret file** — `gmeet.py` reads `.claude/google-oauth-client.json`,
  falling back to the existing `.claude/gmail-oauth-client.json`. Same GCP
  installed-app client works for any scope; tokens are cached separately
  (`gmeet-token-*.json`), so no re-consent disruption to Gmail.
- **Folder discovery** — optional `drive_folder_id` config; auto-resolve by name
  as fallback, with a clear error if the narrow scope blocks it.
- **Account loop** — flat single-tenant like jamie.

## Deferred: Meet REST API enrichment

A later upgrade could enrich the `## Transcript` section with per-utterance
timestamps from the Meet REST API v2 (`conferenceRecords.transcripts.entries`).
Deferred because the marginal value (timestamps) is small and the constraints
are large: `conferenceRecords.list` is organizer-only, records expire 30 days
after the conference, and entry speakers are resource names needing extra
`conferenceRecords.participants` resolution calls. Revisit only if per-utterance
timestamps turn out to matter for compile.py distillation.

## Done when

`wiki collect gmeet` pulls Gemini meeting transcripts + notes from the Drive
"Meet Recordings" folder into `raw/transcripts/gmeet/`; the piggyback auto-runs
every 6 h; OAuth is bootstrapped once via `wiki gmeet-auth`.
