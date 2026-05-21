# Setup: gmeet — ingest Google Meet / Gemini transcripts

`collectors/gmeet.py` exports the Gemini-generated transcript + "Notes by Gemini"
Google Docs from a Drive **"Meet Recordings"** folder into `raw/transcripts/gmeet/`,
**one meeting → one `.md`** with Notes + Transcript sections paired into one
article (across runs, via a stable meeting-key derived from the title).
Multi-tenant: configure one or more accounts under `personal.accounts.<id>.gmeet`,
run `wiki gmeet-auth <id>` once per account, then the 6-h piggyback (or
`wiki collect gmeet`) keeps them flowing.

This is the operator walkthrough. For the architecture, see
`.ytstack/backlog/gmeet-collector.md`; for hard-won learnings see
`.ytstack/KNOWLEDGE.md` "The purpose-built API isn't always the right one".

## Why gmeet exists

Google Meet + Gemini ("Take notes with Gemini") drops two Google Docs into the
recording user's Drive "Meet Recordings" folder per meeting:

- `<title> — Notes by Gemini` (AI summary + action items)
- `<title> — Transcript` (speaker-diarised transcript text)

Both are exportable as markdown via the Drive API. gmeet ingests them so they
flow into the wiki compile pipeline like any other transcript substrate.

The Meet REST API was evaluated and **rejected**: organizer-only, 30-day TTL on
records, transcript-entry speakers are unresolved resource names. The Drive-Doc
export covers organized + attended meetings, persists indefinitely, is already
diarised. See KNOWLEDGE.md for the full research.

## Prerequisites — once per install

You only do this section once for the whole install (multiple accounts share one
GCP OAuth client + one client-secret file).

### 1. GCP project + Drive API + OAuth consent screen

In the [Google Cloud Console](https://console.cloud.google.com):

1. **Project**: pick one (e.g. an existing personal one, or create `llm-wiki-XXXX`).
   Note the `project_id`.
2. **Enable Drive API**: APIs & Services → Library → search **"Google Drive API"** → *Enable*.
3. **OAuth consent screen**: APIs & Services → OAuth consent screen
   - User Type **External** (Internal only if you have a Workspace org and only org users will use it)
   - Publishing status: **Testing** is fine for personal use
   - Edit App → **Scopes** → *Add or Remove Scopes* → filter `drive.meet.readonly`
     (the dedicated narrow scope for files Meet creates) → ✓ → *Update* → *Save*
   - **Test users**: add the email of *every* Google account you'll bootstrap
     gmeet for. In Testing mode, only listed test users can complete the consent
     flow.
4. **OAuth client**: APIs & Services → Credentials → *Create Credentials* →
   "OAuth client ID" → Application type **"Desktop app"** → Name anything →
   *Create* → **Download JSON**.

### 2. Place the client secret

Drop the downloaded JSON at the **neutral** filename so it works for any future
Google-API integration:

```bash
LXW="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<your-vault>"
mv ~/Downloads/client_secret_*.json "$LXW/.claude/google-oauth-client.json"
```

Older installs may have a `.claude/gmail-oauth-client.json` from the Gmail-API
collector setup. gmeet falls back to that file if the neutral name isn't
present, so reusing the existing Gmail client works too — but the neutral
filename is preferred since the same client serves both `gmail-auth` and
`gmeet-auth` (just different scopes).

Sanity-check the file is the real thing (not a stub):

```bash
jq 'paths(scalars) | join(".")' "$LXW/.claude/google-oauth-client.json"
# Real Google JSONs have all 7 fields under .installed:
#   client_id, project_id, auth_uri, token_uri,
#   auth_provider_x509_cert_url, client_secret, redirect_uris
```

A 326-byte file with only 5 fields is a placeholder/stub — re-download from GCP.

## Per-account setup

For each Google account whose **own My Drive** "Meet Recordings" you want to
ingest. Workspace caveat: if your organisation's admin has redirected Meet
recordings to a *Shared Drive*, `drive.meet.readonly` won't see them — the
collector only reads files that account itself owns.

### 3. Add the per-account `gmeet:` sub-block to `config.yaml`

Under `personal.accounts.<account-id>` add a `gmeet:` sub-block. The
`<account-id>` becomes the OAuth token-cache suffix (`gmeet-token-<id>.json`)
and the `account_id` field in every ingested file's frontmatter — pick something
meaningful.

```yaml
personal:
  accounts:
    yesterday-work:                       # <- account-id of your choice
      email: alex@yesterday-ai.de         # used for label/email-collector context
      label: "Yesterday Workspace"
      reader:                             # optional — only if you also ingest mail
        kind: thunderbird-mbox
        mbox_paths: ["ImapMail/imap.gmail-1.com"]
      gmeet:                              # <- the new sub-block
        kind: gmeet-api                   # discriminator; required
        # drive_folder_id: "1AbC..."      # optional; copy from "Meet Recordings" folder URL
        drive_folder_name: "Meet Recordings"   # auto-resolve fallback if drive_folder_id is empty
        # since: "2026-01-01"             # optional; ISO date backfill cap; empty = no cap
        # max_per_run: 50                 # optional; null = inherit CONFIG.limits.gmeet_max_per_run
```

`drive_folder_id` is **optional but recommended for production**. Auto-resolve
by name works (the folder is Meet-created and in scope) but is name-collision-
prone — a Workspace user with a personal "Meet Recordings" + a shared-drive
"Meet Recordings" gets unpredictable results. Every run with an unpinned id
emits a `WARNING` log surfacing the resolved id so you can paste it back into
config. If auto-resolve outright fails, the dry-run says:
`folder 'Meet Recordings' not found — set personal.accounts.<id>.gmeet.drive_folder_id`.
Get the id from the folder URL in your browser:
`https://drive.google.com/drive/folders/<DRIVE_FOLDER_ID>`.

### 4. Bootstrap OAuth — once per account

```bash
wiki gmeet-auth <account-id>
# → opens a local-loopback browser
# → Google account picker → choose the account that owns "Meet Recordings"
# → review the drive.meet.readonly scope → Allow
# → token cached at .wiki/state/gmeet-token-<account-id>.json
```

Repeat for each account you added a `gmeet:` sub-block for. Each gets its own
token cache.

### 5. First run

```bash
# Smoke-test what will happen — no files written:
wiki collect gmeet --dry-run

# When happy, the live run:
wiki collect gmeet                # full sweep (respects per-account `since:`)
wiki collect gmeet --incremental  # delta since last `last_seen_ts` (what the piggyback does)
```

Output lands in `<vault>/raw/transcripts/gmeet/<date>--<slug>--<key>.md` where
`<key>` is the meeting-key — a 12-char hash of the meeting title (with
quote-glyph + whitespace variation normalised away). The same meeting's Notes
Doc and Transcript Doc share a key, so they land in **one file with two
sections** (`## Summary` from Notes, `## Transcript` from Transcript). If a
Notes Doc arrives in run N and the Transcript Doc only shows up in run N+1
(Gemini's generation timing varies), the second Doc is merged into the
existing file rather than written as a duplicate. Skip-existing covers both
filename suffix AND every `drive_docs[*].id` recorded in frontmatter, so
re-runs are safe.

The piggyback runs every 6 h after `compile_after_hour` (per
`config.yaml:piggybacks.gmeet`). If you want to disable it for a particular
install, set `piggybacks.gmeet.enabled: false`.

## Email-discovery — colleague-shared meetings

The folder-scan above only sees meetings **your own** account recorded (the docs
in *your* "Meet Recordings" folder). When a colleague records a meeting you were
invited to, Gemini auto-shares the notes Doc org-wide and emails every attendee
a `gemini-notes@google.com` notification — but that Doc lives in *their* Drive,
so the folder-scan never finds it.

Email-discovery is the second source. It scans this account's mailbox (using the
same `reader` you already configured for the email-collector — Thunderbird mbox /
IMAP / Gmail), follows the `docs.google.com/document/d/<id>` link in each
`gemini-notes@google.com` mail, and exports that Doc through the same pipeline.
The `drive.meet.readonly` scope reads the colleague's Doc because the file is
Meet-origin and shared with you — no extra consent.

It's **on by default** for any account with a `gmeet` block, gated by the sender
allowlist + your configured reader:

```yaml
personal:
  accounts:
    <id>:
      gmeet:
        kind: gmeet-api
        email_discovery:
          enabled: true                       # set false to opt out
          senders: ["gemini-notes@google.com"]
          folder: "INBOX"                      # reader folder to scan
          backfill_days: 30                    # windowed re-scan; raise once to backfill history
```

Discovery is a **windowed re-scan** (last `backfill_days`) deduped by Drive
file-id — idempotent, no separate watermark. To pull in older colleague
meetings once, bump `backfill_days` for a single run, then lower it again.
Requires a working `reader` for the account; with no reader it logs and skips
(folder-scan results still ship).

## State + idempotency

- `state/gmeet-state.json` carries `{<account-id>: {last_seen_ts: …}}` —
  per-account watermarks. Incremental runs query Drive for Docs created
  after each watermark.
- A failed account leaves its watermark untouched — the next run retries the
  same window. Other accounts in the same run scan + advance normally.
- Skip-existing is two-layered: filename suffix (meeting-key) AND every
  `drive_docs[*].id` recorded inside each existing file's frontmatter. The
  latter is what makes "Notes already merged, only Transcript is new" runs
  idempotent. Even with no watermark and `since: ""`, you won't re-ingest a
  Doc; you'll just merge a paired one if it arrived after the original.

## Troubleshooting

**"no-op (no gmeet accounts configured)"** — no `personal.accounts.<id>` has a
`gmeet:` sub-block with `kind: gmeet-api`. Re-check Step 3.

**"auth: Google Meet OAuth credentials missing for '<id>'"** — token cache
absent. Run `wiki gmeet-auth <id>`.

**"Missing OAuth client config: …/google-oauth-client.json"** — the client
secret isn't where gmeet looks. Re-do Step 2.

**"folder 'Meet Recordings' not found"** — auto-resolve failed (rare under
`drive.meet.readonly` for the Meet-created folder, but possible for renamed
folders or Workspace-policy edge cases). Get the id from the folder URL and
add `drive_folder_id: "..."` to the account's `gmeet:` block.

**"403 on GET …"** — usually one of: scope `drive.meet.readonly` not granted at
consent (re-run `wiki gmeet-auth <id>` and double-check the consent dialog
listed it); the account isn't a Test user on the OAuth consent screen
(Step 1.3); a Workspace policy blocks Drive API for that account.

**"401 from Drive — token invalid or scope not granted"** — token expired and
refresh failed. Re-run `wiki gmeet-auth <id>` to re-issue consent.

**Recordings not visible** — the operator's My Drive needs the "Meet Recordings"
folder. If your meetings are recorded but the folder doesn't exist, that
account either never had a Gemini-recorded meeting, or the recording is in a
Shared Drive (admin policy) — `drive.meet.readonly` doesn't reach Shared Drives.

## Multi-tenant policy

`gmeet` was lifted multi-tenant on 2026-05-15 (was flat `personal.gmeet` before).
The architecture policy (DECISIONS.md "2026-05-15: Architecture policy —
account-bound collectors/adapters multi-tenant from day one") locks the rule:
**every account-bound collector goes straight to `personal.accounts.<id>.<service>`
with a `kind:` discriminator, mirroring the existing `reader:` / `filter:`
sub-block pattern.** No more flat single-tenant blocks for account-scoped
integrations.
