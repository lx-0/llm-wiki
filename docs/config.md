# Config Reference

Every settable key in `<vault>/.wiki/config.yaml`, plus the secrets surface in `<vault>/.claude/.env`. Dataclass defaults live in `scripts/core/config.py` — only the keys you want to *override* need to appear in `config.yaml`. Missing keys silently fall back to the default.

## Contents

- [Files at a glance](#files-at-a-glance)
- [Section index](#section-index)
- [scheduling](#scheduling)
- [models](#models)
- [features](#features)
- [limits](#limits)
- [piggybacks](#piggybacks)
- [graph_view](#graph_view)
- [skills](#skills)
- [personal](#personal) — primary account, accounts (with per-service sub-blocks: reader/filter/gmeet/jamie), email folders, scanners
- [Secrets — `.claude/.env`](#secrets--claudeenv)

Run `./.wiki/wiki config keys` for the live, full list of every leaf key the dataclass exposes.

## Files at a glance

| File | Purpose | Tracked? |
|---|---|---|
| `<engine>/config.example.yaml` | Engine-shipped defaults + comments. Copied once at install. | yes |
| `<vault>/.wiki/config.yaml` | Per-install overrides. Read by every script via `core.config.CONFIG`. | gitignored |
| `<vault>/.claude/.env` | Secrets (API keys, IMAP passwords). Loaded by `core.config` at import. | gitignored |
| `<vault>/.claude/.env.example` | Catalogue of every env-var the engine recognises. Seeded by `wiki seed`. | tracked (template) |

The `.env` file: only the **variable NAME** lives in `config.yaml` (e.g. `api_key_env: JAMIE_WORK_API_KEY`); the **value** lives in `.env`. Shell exports override `.env` values (`override=False` policy). A missing `.env` is a clean no-op.

## Section index

| Section | Lives in |
|---|---|
| `scheduling.*` | `Scheduling` dataclass |
| `models.*` | `Models` dataclass |
| `features.*` | `Features` dataclass |
| `limits.*` | `Limits` dataclass |
| `piggybacks.<task>.*` | `PiggybackTask` dataclass per task |
| `graph_view.*` | `GraphView` dataclass |
| `skills.*` | `Skills` dataclass |
| `personal.*` | `Personal` dataclass (accounts hold per-service sub-blocks: `reader`, `filter`, `gmeet`, `jamie`) |

## scheduling

| Key | Default | Meaning |
|---|---|---|
| `scheduling.compile_after_hour` | `18` | Hour-of-day (`0`–`23`, local time) at which auto-compile + piggyback tasks may spawn from `flush.py`. Set to `0` to disable the time-gate. |
| `scheduling.dedup_window_seconds` | `60` | Dedup window for repeated session-flushes of the same session id. |
| `scheduling.timezone` | `"UTC"` | IANA timezone name (`Europe/Berlin`, `America/New_York`, …). Drives `compile_after_hour` cutoff + daily-log filename + `reviewed` timestamps. |

## models

| Key | Default | Meaning |
|---|---|---|
| `models.compile_model` | `"claude-opus-4-7"` | Claude model used by `compile.py` + `retry-failed-flushes.py`. Options: `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`. |
| `models.ollama_url` | `"http://localhost:11434"` | Ollama endpoint for every local-LLM call. |
| `models.vision_model` | `"gemma4:e4b"` | Vision model for screenshot OCR + YouTube Tier-3 frame analysis. |
| `models.curiosity_model` | `"gemma4:e4b"` | Curiosity-loop gap-detection model (compile post-pass). |
| `models.classify_model` | `"gemma4:e4b"` | Inbox classifier. |

## features

Master switches for entire capabilities. Disable when the dependency (Ollama, webmail API, browser extension) isn't available.

| Key | Default | Meaning |
|---|---|---|
| `features.curiosity_loop` | `true` | Gap detection after each compile run. Writes follow-up requests to `raw/requests/`. |
| `features.vision_screenshots` | `true` | Local vision OCR for `scan-screenshots`. |
| `features.procmail_execution` | `true` | Allow `suggestions/cli.py` to call webmail Procmail APIs. Default off in `config.example.yaml` (kasserver-specific). |
| `features.clippings_sweep` | `true` | Pre-compile sweep of `<vault>/Clippings/*.md` into `<vault>/raw/articles/`. Disable if Obsidian Web Clipper drops directly into `raw/articles/`. |
| `features.materialize_backlinks` | `true` | Corpus-wide post-compile pass writes a sentinel-managed `## Backlinks` footer into every `knowledge/<article>.md`. Idempotent — unchanged corpus produces zero writes. Flip false to skip the sweep (compile-timing comparison, or operator wants to manage backlinks differently). |

## limits

Knob block. Defaults sized for an Opus-on-5h-window install — tighten on smaller plans.

### Compile + flush

| Key | Default | Meaning |
|---|---|---|
| `limits.compile_max_files` | `30` | Per-run cap (rate-limit guard for the 5h Opus window). |
| `limits.compile_max_consecutive_failures` | `3` | Abort after N back-to-back compile failures. |
| `limits.compile_max_prompt_chars` | `400000` | Pre-flight cap on the assembled compile prompt. Trips with a clear breakdown instead of 13 min of silent `kind=unknown`. |
| `limits.compile_max_turns` | `12` | Tool-turn ceiling per compile run. Was 30 — large sources looped on Read/Grep into `knowledge/` until they blew the context window. |
| `limits.compile_large_source_chars` | `50000` | At/above this source size, auto-upgrade to `models.compile_large_source_model` (1M-context Opus). Catches deterministic overflows. |
| `limits.compile_retry_long_context_on_unknown` | `true` | On `kind=unknown` failure (stochastic context overflow from tool fan-out), retry once with `models.compile_large_source_model`. Catches small-source overflows the size-threshold misses. Set false to surface the failure instead. |
| `limits.compile_force_long_context_types` | `["daily-digest"]` | Substrates whose compile reliably fans out into many existing articles (matched by frontmatter `type:`). Forces `models.compile_large_source_model` up-front regardless of source size — daily-digest is <2 KB but references 6+ topics, blowing the 200K window mid-stream. Empty list disables the override. |
| `limits.compile_skip_on_long_context_unknown` | `true` | Treat `kind=unknown` failures with no further retry path (small source OR already on the 1M model) as skips instead of hard failures. Preserves the consecutive-failure budget so the batch survives a structurally-unprocessable file. Set false to surface every `kind=unknown` as a failure (legacy pre-2026-05-15 behavior). |
| `limits.flush_max_retries` | `3` | Retries for flush-extraction calls. |
| `limits.flush_retry_delay_seconds` | `30` | Delay between flush retries. |

### Screenshots

| Key | Default | Meaning |
|---|---|---|
| `limits.screenshot_resize_width` | `512` | Pixel width before sending a screenshot to the vision model. |
| `limits.screenshot_timeout_seconds` | `60` | Per-screenshot Ollama timeout. |

### Curiosity loop

| Key | Default | Meaning |
|---|---|---|
| `limits.curiosity_max_gaps` | `3` | Max curiosity-requests written per compile run. |
| `limits.curiosity_min_source_chars` | `500` | Skip curiosity for sources shorter than this. |
| `limits.curiosity_timeout_s` | `240` | Ollama timeout for the gap-detection call (long YT-notes hit >90 s on gemma4:e4b). |

### Lint

| Key | Default | Meaning |
|---|---|---|
| `limits.sparse_threshold_words` | `200` | Lint warns under this word count per article. |

### YouTube ingest (Tier-3 visual)

| Key | Default | Meaning |
|---|---|---|
| `limits.youtube_max_frames` | `30` | Cap frames per video. |
| `limits.youtube_max_duration_s` | `10800` | Skip videos longer than this (3 h). |
| `limits.youtube_frame_resize_width` | `512` | `ffmpeg` downscale before vision model. |
| `limits.youtube_vision_timeout_s` | `90` | Per-frame Ollama timeout. |
| `limits.youtube_aggregate_timeout_s` | `300` | Final synthesis Ollama timeout. |

### Jamie ingest

| Key | Default | Meaning |
|---|---|---|
| `limits.jamie_request_timeout_s` | `30` | Per-HTTP-call timeout against `beta-api.meetjamie.ai`. |
| `limits.jamie_max_per_run` | `50` | Default cap on meetings pulled per run per account. Per-account override lives at `personal.accounts.<id>.jamie.max_per_run`. |

### Claude Agent SDK

| Key | Default | Meaning |
|---|---|---|
| `limits.sdk_max_buffer_size_mb` | `50` | Per-message buffer for stream-json output from the bundled CLI. SDK default is 1 MB; trips on tool-result messages carrying `knowledge/index.md` (~300 KB raw → ~600 KB JSON-escaped) or Write/Edit calls on large articles with a confusing `Failed to decode JSON: ... exceeded maximum buffer size of 1048576 bytes` exception. 50 MB is safe headroom; bump higher if `knowledge/` grows past ~5 MB per article. |
| `limits.query_max_prompt_chars` | `500000` | Pre-flight cap for `wiki query` prompts. `query.py` checks `len(prompt)` before the SDK call and aborts with a clear `PromptTooLargeError` message (size + limit + per-component breakdown) instead of the opaque exit-1 / empty-stderr death an oversized prompt causes inside the bundled CLI. ~167K tokens at German density — inside a 200K-token window with response headroom. Raise it if you run a larger-context model. |

### Hard facts — `wiki correct apply` (M028, issue #5)

| Key | Default | Meaning |
|---|---|---|
| `limits.correct_apply_max_turns` | `50` | Tool-turn ceiling for the operator-driven `wiki correct apply` agent. Broader than `concept_reconcile_max_turns` (it propagates one fact across the whole vault), so a larger bound. Was a hardcoded 50 before `apply()` was sandboxed. |
| `limits.correct_broad_term_threshold` | `15` | `wiki correct add` warns (non-blocking) when a `negation_term` matches more than this many existing articles — an over-broad term becomes lint noise or, via `apply`, a large blast radius. |

## piggybacks

Recurring tasks spawned by `flush.py` after `compile_after_hour`. Each entry takes `enabled` (bool), `cooldown_hours` (int), and optionally `max_per_run` (int).

| Key | Default | Cap | Notes |
|---|---|---|---|
| `piggybacks.email` | `enabled: true, cooldown_hours: 24` | — | `EmailCollector` — incremental mailbox sweep. (Renamed from `email_incremental` in M002.) |
| `piggybacks.lint_structural` | `enabled: true, cooldown_hours: 24` | — | No-LLM structural lint sweep. |
| `piggybacks.review_wiki` | `enabled: true, cooldown_hours: 168` | — | Weekly per-article quality-score via local Ollama. |
| `piggybacks.optimize_claude_md` | `enabled: true, cooldown_hours: 24` | — | Suggests CLAUDE.md edits from compiled patterns. |
| `piggybacks.scan_screenshots` | `enabled: true, cooldown_hours: 24` | `max_per_run: 50` | Local-vision OCR of new screenshots. |
| `piggybacks.scan_youtube` | `enabled: true, cooldown_hours: 24` | `max_per_run: 10` | Drains the YouTube inbox file. |
| `piggybacks.jamie` | `enabled: true, cooldown_hours: 6` | `max_per_run: 20` | Pulls new meetings from the Jamie API. Tighter cooldown — meetings are time-sensitive. |
| `piggybacks.gmeet` | `enabled: true, cooldown_hours: 6` | `max_per_run: 20` | Drive-API export of Gemini Meet transcripts. Tighter cooldown — meetings are time-sensitive. |
| `piggybacks.voice` | `enabled: true, cooldown_hours: 1` | — | Folder-watch on `personal.voice_inbox`. Tight cooldown — voice notes are time-sensitive. |
| `piggybacks.follow_requests` | `enabled: true, cooldown_hours: 24` | — | Acts on `raw/requests/` items from the curiosity loop. |
| `piggybacks.retry_failed_flushes` | `enabled: true, cooldown_hours: 24` | `max_per_run: 5` | Re-processes archived flush contexts. |

## graph_view

Drives `.obsidian/graph.json` rebuilds by `wiki seed`.

| Key | Default | Meaning |
|---|---|---|
| `graph_view.mode` | `"knowledge-only"` | One of: `knowledge-only`, `full-vault`, `sources-only`, `custom`. |
| `graph_view.custom_search` | `""` | Obsidian search expression when `mode=custom`. |

## skills

Engine-skill distribution. Most bundled skills operate *inside* a vault and are always linked vault-locally into `<vault>/.claude/skills/`. A few are global-eligible — they let an agent in *any* project discover and use this wiki — and can additionally be linked into `~/.claude/skills/`.

| Key | Default | Meaning |
|---|---|---|
| `skills.global_install` | `false` | When `true`, `wiki skills install` / `wiki skills sync` also link global-eligible skills (currently `use-llm-wiki`) into `~/.claude/skills/` and register this vault's root in `~/.config/llm-wiki/vaults` (the discovery registry the `use-llm-wiki` skill reads). The `--global` / `--no-global` flags on `wiki skills install` are one-shot shortcuts that write this key — it is the durable opt-in, so an opted-in vault stays globally linked across `wiki update`. The setup wizard's 6th question sets it too. |

The registry file `~/.config/llm-wiki/vaults` (honours `XDG_CONFIG_HOME`) is plain newline-delimited vault-root paths — engine state, not a tracked artefact, and the only thing the engine writes outside the vault.

## personal

Per-instance data — operator-specific. **Never committed** (lives in `config.yaml`, gitignored). `config.example.yaml` ships empty defaults so prompts and schemas render cleanly on a fresh install.

### Top-level

| Key | Default | Meaning |
|---|---|---|
| `personal.primary_account` | `""` | Account id used as default in prompts + fallback in `compile.py`. |
| `personal.output_language` | `"auto"` | Output **prose** language of compiled `knowledge/**` articles. `"auto"` = write in the source material's language (today's behavior, byte-identical compile). A language (`"de"`, `"German"`, `"fr"`, …) forces **all** compiled prose — titles, body, summaries — into that language regardless of source, while keeping code, technical identifiers, proper names, and the canonical structural headers (`## State`, `## Timeline`, …) verbatim. Reaches the compile substrate prompts plus (since 0.2.1) the curiosity + dream-entity render paths. Distinct from `personal.voice_transcribe_language` (input transcription vs. output prose). |
| `personal.thunderbird_profile` | `""` | Absolute path to local Thunderbird profile. Empty disables the Thunderbird-mbox reader + `thunderbird-rules`. |
| `personal.firefox_profile` | `""` | Absolute path to Firefox profile (`Library/Application Support/Firefox/Profiles/<id>.default-release` on macOS). Drives the browser collector. |
| `personal.stg_backup_dir` | `""` | Simple Tab Groups backup dir. Drives the tabs collector STG import path. |

### Accounts (M002+ nested schema)

```yaml
personal:
  accounts:
    work:
      email: alex@example.com           # required — used in prompts + reports
      label: "Work"                     # optional — display label
      reader:
        kind: thunderbird-mbox          # thunderbird-mbox | gmail-api | imap
        mbox_paths:                     # relative to thunderbird_profile
          - ImapMail/server/INBOX.mbox
      filter:
        kind: all-inkl-procmail         # thunderbird-msgfilter | all-inkl-procmail | gmail-api
        imap_user_env: WORK_IMAP_USER   # env var name (not value)
        imap_pass_env: WORK_IMAP_PASS
        imap_host: mail.example.com
```

`reader.kind` and `filter.kind` dispatch independently — an account can read via Thunderbird mbox and write filter rules via All-Inkl Procmail (the legacy hybrid). Unknown kinds are silently skipped (graceful agnostic).

**Reader kinds:**

- `thunderbird-mbox` — reads local mbox files a Thunderbird profile already synced. No credentials in the engine; the mail client owns auth. Keys: `mbox_paths` (relative to `personal.thunderbird_profile`).
- `gmail-api` — Gmail API over OAuth2. Needs an OAuth client at `.claude/gmail-oauth-client.json` and a one-time `wiki gmail-auth <id>`. No extra `reader` keys.
- `imap` — generic IMAP, for accounts with **no local client and no Google Cloud project**. Auth is an IMAP login with a username + **app password**. For Gmail: enable 2-Step Verification, then generate an App Password (`myaccount.google.com/apppasswords`) — it is **16 lowercase letters**; paste those 16 chars into `.env` **without the display spaces** (Google shows it grouped as `xxxx xxxx xxxx xxxx`). Keys: `imap_host` (required), `imap_pass_env` (required — env-var *name* holding the password), `imap_user_env` (optional — env-var name for the username; omit → falls back to `account.email`), `folders` (optional list — only scan these; omit → all folders, which on Gmail includes the `[Gmail]/All Mail` per-label duplicate).

The pre-M002 flat-account schema (`mbox_paths`, `imap_host`, `has_procmail` directly on the account) is rejected at config load with an explicit migration error. Note this only rejects those keys at the *account* level — nested inside `reader:` / `filter:` they are the normal schema.

### Jamie (multi-tenant)

```yaml
personal:
  accounts:
    work:
      email: alex@example.com
      jamie:
        kind: jamie-api
        api_key_env: JAMIE_WORK_API_KEY   # env var holding the jk_... key
        key_type: personal                # personal | workspace
        since: ""                         # ISO date "2026-01-01" — first-install backfill cap
        max_per_run: null                 # null inherits CONFIG.limits.jamie_max_per_run
```

Per-account `jamie:` sub-block with `kind: jamie-api`, mirroring the `reader:` / `filter:` / `gmeet:` pattern. An account with no `jamie:` sub-block is silently skipped; an account whose `api_key_env` resolves to an empty/unset env var is also skipped (graceful-agnostic) — the rest of the loop still runs. State per account at `state/jamie-state.json` keyed by account-id.

### Email folders + scanner-prompt config

| Key | Default | Meaning |
|---|---|---|
| `personal.email_folders` | `[]` | List of `{path, desc}` pairs. Drives both the `compile_curiosity` prompt and `compile.py`'s schema enum — single source of truth. |
| `personal.project_examples` | `[]` | List of project / product names rendered into `scan_screenshots_vision.md` as concrete examples. |
| `personal.calendar_skip_keywords` | `[]` | Substrings marking holidays / observances to skip during `collectors/calendar.py` ingest. Locale-specific (e.g. `["Christmas", "Easter"]` vs. `["Weihnacht", "Ostern"]`). |
| `limits.calendar_request_timeout_s` | `30` | Per-HTTP-call timeout against `calendar.googleapis.com`. |
| `limits.calendar_max_per_run` | `500` | Per-calendar event cap (multiplied by the number of selected calendars). Override per-account via the `max_per_run:` field on the `calendar:` sub-block. |
| `limits.calendar_backfill_days` | `90` | Past window in days on first run (events with `updated >= now-N` for delta sync). Override per-account via `backfill_days:`. |
| `limits.calendar_future_days` | `7` | Future window re-fetched every run — picks up event mutations on upcoming meetings (moved, cancelled, retitled). Override per-account via `future_days:`. |

## Secrets — `.claude/.env`

Loaded automatically at import via `core.config.load_dotenv(<vault>/.claude/.env, override=False)`. Add new entries to `<engine>/templates/.claude/.env.example` to ship them to fresh vaults via `wiki seed`.

| Variable | Used by | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Whisper audio transcription (and future OpenAI paths) | — |
| `JAMIE_<ACCOUNT>_API_KEY` | `collectors/jamie.py` | One per account with a `jamie:` sub-block. Name matches the `api_key_env` field; `<ACCOUNT>` is your choice. Pro/Team/Enterprise plan. `jk_` prefix. Generate in Jamie: Settings → Developers → API Keys. |
| `IMAP_<ACCOUNT>_USER` / `_PASS` | `adapters/mailbox/imap.py` (`imap` reader), `suggestions/backends/imap.py`, `adapters/mailbox/allinkl.py` | `<ACCOUNT>` matches the value of `imap_user_env` / `imap_pass_env` in the account's `reader` (kind: imap) or `filter` block. Gmail needs an App Password — 16 lowercase chars, pasted without the display spaces. |
| `NAS_HOST` / `NAS_USER` / `NAS_PASS` | Future `scan-nas.py` / SMB-backed collectors | — |
| `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` | adhikasp/mcp-linkedin MCP server | **Not loaded from `.env`** — set in `~/.claude.json` under `mcpServers.linkedin.env`. Listed only as a reminder. |

## Editing safely

- **Programmatic edits** (`wiki config set`) round-robin-backup the file to `.wiki/state/config-backups/` (last 10 retained) before writing. PyYAML drops comments on round-trip — manual edits in `$EDITOR` preserve them.
- **Round-trip caveat**: if you `wiki config set` after hand-editing, the next read-back may not match your file byte-for-byte (comment loss, key reordering inside a section). The dataclass semantics survive — values stay correct.
