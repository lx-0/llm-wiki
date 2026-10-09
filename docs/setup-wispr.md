# Wispr Flow meeting collector

`wiki collect wispr` pulls meetings directly from Wispr's HTTP API, like the
Jamie collector. No MCP, agent call, or local meeting-database import is involved.
Summary, notes and full inline refined transcript become one Markdown source
under `raw/transcripts/wispr/`. The existing compiler consumes this source.
The collector adds a daily meeting line with `sources:` provenance.

## Account setup

Configure a `wispr` block under an existing or new `personal.accounts.<id>`
through an instance configuration migration. `wiki config set` can subsequently
change existing scalar fields; it cannot create a new account mapping.
Two authentication options are supported:

```yaml
personal:
  accounts:
    work:
      wispr:
        kind: wispr-api
        access_token_env: WISPR_WORK_ACCESS_TOKEN
```

The named environment variable holds a current **desktop HTTP API access
token**, not a MCP token or a Jamie-style API key. Do not put the token in YAML.
Expired tokens must be replaced. Wispr uses `Authorization: <token>` without a
`Bearer` prefix on this endpoint.

Alternatively, use the already signed-in desktop app's session file:

```yaml
personal:
  accounts:
    work:
      wispr:
        kind: wispr-api
        session_file: ~/Library/Application Support/Wispr Flow/session.json
        user_id: YOUR_WISPR_USER_ID
```

`user_id` must match `workosSession.userId` in that file. It pins the account so
switching the desktop app to another user cannot silently mix sources. The
collector reads only the access token and account ID; it does not write the
session file, copy credentials into wiki state, or rotate the app's refresh
token. The app remains responsible for renewal. Keep Flow signed in; after
HTTP 401, open Flow to renew the session and retry. If `access_token_env` is
specified, it takes precedence and does not fall back to another identity.

## Run

```sh
wiki collect wispr --account work --dry-run
wiki collect wispr --account work
wiki collect wispr --account work --incremental
```

The default piggyback cooldown is six hours, gated on a configured account
and triggered by session flush (not an independent timer).
`limits.wispr_request_timeout_s`, `wispr_max_per_run` and `wispr_max_pages`
bound requests and scans. Config migrations add these tunables to existing
vaults; accounts are always explicit operator configuration.

Repeated imports are idempotent. Changed notes/transcripts update the existing
source path even if the title changes. A bounded run, failed request or unfinished
recording retains the sync watermark so missing content can be retried. A
successful item before a later-page failure still retains its dedup record.
Empty recordings do not create empty wiki sources. Remote deletions are skipped;
they do not delete previously captured local sources.

## API contract and verification

This uses the **desktop backend API**, not a published stable developer API.
The contract was checked in the installed Wispr application and against the
live service on 2026-10-09:

- `POST https://api.wisprflow.ai/api/v1/meetings/sync`
- Body: `meetings: []`, `last_sync_time` (epoch milliseconds as a string),
  `hard_refresh`, `supports_refined_stamp_fetch: false`, optional `cursor`.
- Response: `acked`, `rejected`, `pull`, `sync_time`, `next_cursor`.
- **Every request sends an empty upload list**; recording state is never sent.
- The full inline transcript option avoids MCP character-range pagination.

The initial live account had one finalized meeting but no notes, summary or
transcript. Listing and authentication were verified; full transcript import
is covered by fixture tests and still needs a populated live recording.
Unknown note JSON is preserved verbatim rather than silently discarded.
Schema changes and authentication failures surface as collector errors.

Wispr's separately documented [MCP connection](https://docs.wisprflow.ai/articles/9551372685-connect-an-mcp-client-to-wispr-flow-remote-mcp-server)
is not used by this collector. Normal dictation history is outside this collector's scope.

See the [Jamie and Wispr architecture diagram](meeting-collectors-architecture.md)
for the shared data flow and authentication boundaries.
