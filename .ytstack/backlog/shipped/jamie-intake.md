# Jamie intake — concept + Phase 2 verification

**Status:** Phase 2 (integration verification) — pending user approval before implementation.
**Supersedes:** `meetily-intake.md` (Meetily eval failed on diarization gap). The Meetily doc stays as a rejected-alternative ADR.
**Related memory:** `project_meeting_intake_candidates.md` (to be updated post-implementation).

## Architecture decision: Collector, not scan-* script

`scan-youtube.py` is a one-shot CLI tool — it has no notion of accounts and writes one substrate. Jamie has:
- Account-typed access (personal-key vs workspace-key, different routes)
- Network backend (HTTP API, rate-limit + auth)
- Future second backend possible (Otter / Granola if user ever migrates)

→ The right shape is `Collector` (substrate-orchestrator) with the Jamie HTTP client lives inline. **No adapter family yet.** Adding `adapters/meetings/` parallel to `adapters/mailbox/` is premature abstraction with a single backend. Extract when a 2nd meeting-tool actually ships.

Pattern mirrors `EmailCollector` exactly:
- `SPEC = CollectorSpec(name="jamie", output_subfolder="raw/transcripts/jamie", piggyback_default=True, ...)`
- `is_configured()` returns True iff API key env-var resolves to a non-empty value
- `run(dry_run, incremental)` fetches meetings → writes one MD per meeting

flush.py needs **zero changes** — `piggyback_collectors()` auto-discovers any `@register`-decorated class.

## What the Jamie API gives us

Confirmed live (2026-05-13):

| Endpoint | Purpose | Used by collector |
|---|---|---|
| `GET /v1/me/meetings` | list (date-range, email, tag, pagination) | yes (incremental scan) |
| `GET /v1/me/meetings/{id}` | full: summary, transcript, participants, tasks, tags, calendar event | yes (per-meeting render) |
| `GET /v1/me/meetings/search` | semantic search | not in initial scope |
| `GET /v1/me/tasks` | action items across meetings | not in initial scope (already in `/meetings/{id}` payload) |
| `GET /v1/me/tags` | tag catalogue | not in initial scope |
| `DELETE /v1/me/meetings/{id}` | destructive — never called |
| Webhook `meeting.completed` | push-based ingest trigger | deferred (separate follow-up — needs public endpoint) |

`workspace`-key uses `/v1/workspace/...` route prefix; routes are identical otherwise. Single per-account decision: `key_type = personal | workspace`.

Auth: `Authorization: Bearer jk_...` per Jamie docs. (Verify on first request — if it's a different header form, adjust at implementation time.)

## Output: one markdown per meeting

Path: `<vault>/raw/transcripts/jamie/<date>--<slug>--<short-id>.md`
Example: `2026-05-13--standup-team-platform--a7f3b2e0.md`

Frontmatter:

```yaml
type: transcript
source: jamie
meeting_id: <jamie-uuid>
title: <meeting title>
started_at: <ISO8601>
ended_at: <ISO8601>
duration_min: <int>
participants:                  # always populated — Jamie does this well
  - {name: "Alex", email: "alex@example.com"}
  - {name: "Sidney", email: "sid@example.com"}
calendar_event: <id or null>
tags: [jamie, meeting, <jamie-tag-1>, <jamie-tag-2>]
ingested_at: <ISO8601>
input_source: cli|piggyback
account_id: <which configured account fetched this>
key_type: personal|workspace
jamie_url: https://app.meetjamie.ai/m/<id>
```

Body sections (only emitted when source data present):

1. **Header line** — `_<duration_min> min · <participants joined> · <date>_`
2. **Summary** — Jamie's structured summary verbatim (already markdown-formatted)
3. **Action items** — bullet list from `/meetings/{id}` payload, `- [ ] <owner>: <task>` shape
4. **Transcript** — speaker-labeled (Jamie does diarisation properly), `**<speaker>** [mm:ss] — <text>`. `[mm:ss]` anchor matches youtube-intake convention.

## Config schema

```yaml
personal:
  jamie:
    # Required env var name holding the jk_... API key. Empty/unset → collector skipped.
    api_key_env: JAMIE_API_KEY
    # personal | workspace — selects /v1/me vs /v1/workspace route prefix.
    key_type: personal
    # Optional: cap how many meetings get pulled in one run.
    # Default in `Limits` block; this lets a user pin it per-account.
    max_per_run: null
    # Optional: ISO date string. Collector ignores meetings with started_at < since.
    # Useful for first install when you don't want to ingest 2 years of history.
    since: "2026-01-01"
```

This is a **flat `personal.jamie` block**, NOT a `personal.accounts.<id>` entry — because Jamie is single-tenant per install (one Jamie account = one user). If a future use-case needs multi-account, we lift it into `personal.accounts` then.

Plus:

```yaml
piggybacks:
  jamie:
    enabled: true
    cooldown_hours: 6
    max_per_run: 20
```

And:

```yaml
limits:
  jamie_request_timeout_s: 30
  jamie_max_per_run: 50           # default cap; piggybacks.jamie.max_per_run overrides per-piggyback
```

## Files affected — exact diff plan

| # | File | Change | Insertion point |
|---|---|---|---|
| 1 | `scripts/collectors/jamie.py` | NEW. ~180 LOC: JamieClient (inline HTTP), JamieCollector. Mirrors email.py shape. | New file |
| 2 | `scripts/collectors/__init__.py` | `from collectors import jamie` (1 line, after email import) | After line 19 |
| 3 | `scripts/wiki_config.py` | Add `JamieConfig` dataclass; extend `Personal` with `jamie: JamieConfig`; add `jamie` PiggybackTask default; add `jamie_request_timeout_s` + `jamie_max_per_run` to `Limits` | `Personal` class (~line 96), `Limits` class (~line 56), `_default_piggybacks` (~line 156) |
| 4 | `config.example.yaml` | Add `personal.jamie` block (with comment + example), `piggybacks.jamie`, `limits.jamie_*` | Match existing structure |
| 5 | `AGENTS.md` | Add `raw/transcripts/jamie/` row to "raw/ substrates" table; mention Jamie under source types | The substrate table section |
| 6 | `docs/PROCESS.md` | Add ingest pipeline section (mermaid + edge case table) | After existing ingest sections |
| 7 | `README.md` | One-line example `wiki collect jamie` near other collector examples | Existing CLI examples block |
| 8 | `.ytstack/KNOWLEDGE.md` | Hard-won entry IF something fights us in implementation (Jamie API quirk, auth header form, rate-limit pattern). Skip if smooth. | "Hard-won learnings" section |
| 9 | `docs/architecture.excalidraw` | Add Jamie node + arrow into `raw/transcripts/` | Architecture diagram |
| 10 | `docs/vault-tour.excalidraw` | Add `raw/transcripts/jamie/` to vault tree | Vault tour diagram |

No changes to `flush.py` (Registry auto-discovery), `wiki` CLI dispatcher (`wiki collect jamie` already routes via `cmd_collect`), or any other script.

## Edge cases

| Case | Behavior |
|---|---|
| `JAMIE_API_KEY` env var unset | `is_configured()` returns False → piggyback skips silently; `wiki collect jamie` prints "not configured". |
| API returns 401 | Log + abort run; do not retry. Stale/revoked key needs operator action. |
| API returns 429 (rate-limit) | Respect `Retry-After` header; sleep + retry once. If second hit: abort, log to `.wiki/logs/jamie-<date>.log`. |
| API returns 5xx | Single retry with 5s backoff. Persistent → abort run, no partial commit. |
| Meeting already on disk (same `meeting_id`) | Skip-existing. `--no-skip` (not yet wired through `wiki collect`) re-writes. Phase 3 will wire if needed. |
| `incremental=True` | Query `?since=<state.jamie_last_seen_ts>`; on success update state. Empty response = no-op. |
| `incremental=False` (default `wiki collect jamie`) | Full scan from `personal.jamie.since` (or no filter if unset). |
| Transcript missing in `/meetings/{id}` payload (Jamie still processing) | Render summary-only file with `transcript_status: pending` frontmatter. Next incremental run re-checks. |
| Title contains slashes / unicode | `slugify()` reuse from `scan-youtube.py` — already proven. |
| Network down | Connection refused → abort with one-line warning, no partial state mutation. |
| API schema change (Jamie pushes v2) | Frontmatter records `api_version: v1`. When v2 ships, version-pin guard mirrors what we'd planned for Meetily SQLx migrations. |

## What this concept does NOT include

- **Webhooks** — push-based ingest deferred. Needs public HTTPS endpoint (tunnel via Cloudflare/Tailscale). Worth doing when polling proves too slow; not before.
- **Search endpoint** — `/meetings/search` is for query-time, not ingest-time. If wiki query-side ever needs Jamie-semantic-search, separate feature.
- **DELETE** — destructive, never called from this collector.
- **Two-way sync** — wiki cannot write back to Jamie. One-way only.
- **Audio file download** — Jamie may offer audio export; not in initial scope (the wiki has no audio surface).
- **Per-tag filtering** — initial scope ingests everything; tag-based filtering deferred until corpus grows enough to need it.

## Open questions for review

1. **Single-tenant assumption.** Concept proposes flat `personal.jamie` block (one Jamie account per install). If you ever need both personal + workspace keys in parallel, we'd lift it into `personal.accounts.<id>` with a new `kind: jamie-api`. **Confirm single-tenant is fine for now?**

2. **Output path.** `raw/transcripts/jamie/` matches the Meetily-intake decision. Alternative is `raw/notes/jamie/` to mirror YouTube. Recommend `raw/transcripts/` since meetings ARE transcripts and the constant already exists. **Confirm preference.**

3. **`since` default.** Default is `null` (no time filter) — first install on a 2-year-old Jamie account would pull everything. Alternative: default to 90 days back. **Confirm preference.**

4. **Action items as wiki tasks.** Render as `- [ ] <owner>: <task>` (Obsidian-task-plugin-compatible) vs `- **<owner>**: <task>` (plain). First option makes them queryable via wiki tasks-plugin if you use it. **Confirm preference.**

5. **Speaker time anchors.** YouTube uses `[mm:ss]` post-text; Jamie API likely returns segments with start times. Concept proposes `**<speaker>** [mm:ss] — <text>` (speaker first, then anchor). **Confirm or specify alternative.**

6. **Phase 3 readiness.** When you say "go", I implement files #1–#4 first (collector + config), test against the test summary in your Jamie account, then docs (#5–#7), then infographics (#9–#10). **Confirm this order, or pull docs/infographics ahead?**
