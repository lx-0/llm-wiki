# Meeting collector architecture

Jamie and Wispr Flow use the same collector pipeline: direct HTTP requests,
one Markdown source per meeting, daily provenance, then the existing compiler.
Authentication and the provider's API contract stay inside each collector.

```mermaid
flowchart TB
    trigger["wiki collect / session-flush piggyback"]

    subgraph providers["Meeting services"]
        jamieAPI["Jamie HTTP API"]
        wisprAPI["Wispr desktop HTTP API"]
    end

    subgraph engine["Engine · .wiki/"]
        registry["Collector registry + account loop"]
        jamie["Jamie collector"]
        wispr["Wispr collector"]
        state["Per-account sync state + deduplication"]
        compiler["Existing wiki compiler"]
    end

    key["Jamie API key · environment"] -. authentication .-> jamie
    session["Wispr app session · read-only access token + pinned user ID"] -. authentication .-> wispr
    trigger --> registry
    registry --> jamie
    registry --> wispr
    jamieAPI -->|"summary + transcript + action items"| jamie
    wisprAPI -->|"summary + notes + inline transcript"| wispr
    jamie --> state
    wispr --> state

    subgraph vault["Vault · operator data"]
        rawJamie["raw/transcripts/jamie/*.md"]
        rawWispr["raw/transcripts/wispr/*.md"]
        daily["daily/date/meetings.md · sources provenance"]
        knowledge["knowledge/ · people, projects, concepts"]
    end

    jamie --> rawJamie
    wispr --> rawWispr
    jamie --> daily
    wispr --> daily
    rawJamie --> compiler
    rawWispr --> compiler
    daily --> compiler
    compiler --> knowledge
```

## Wispr request and persistence

1. Resolve configured `personal.accounts.<id>.wispr` accounts. Read the current
   desktop access token on each request and verify the configured user ID;
   alternatively use the explicitly configured token environment variable.
2. Call `POST /api/v1/meetings/sync` with `meetings: []` and
   `supports_refined_stamp_fetch: false`. Follow response cursors to retrieve
   the full inline meeting content. Requests upload no meetings or recording state.
3. Write finalized, nonempty meetings to stable Markdown paths. Content hashes
   prevent duplicate imports; later edits update the existing source.
4. Add a daily meeting entry with its canonical source in `sources:` frontmatter.
   Keep sync watermarks unchanged while content is pending or a run is incomplete.
5. The normal compile pipeline distills these sources into knowledge articles.

The automatic Wispr collector runs on session flush when its six-hour cooldown
has elapsed and an account is configured. It is a piggyback, not a standalone
six-hour timer. Manual collection uses `wiki collect wispr`.

No MCP server or local meeting-database import is involved. The desktop app
renews its own session; the collector never refreshes or writes app credentials.
The desktop backend is not a published stable API. Empty recordings stay pending
until usable content appears and do not create empty source files.

See [Wispr setup and API contract](setup-wispr.md), the
[high-level overview](overview.png), and the
[full cognitive architecture](architecture.png).
