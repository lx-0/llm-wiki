# CONTEXT.md — Domain + Architecture Glossary

The vocabulary used across this codebase. Single source of truth for naming. New code MUST use these terms; if you're tempted to invent a synonym, update this file instead.

Ordered roughly: domain-level concepts first, architecture concepts second.

## Domain

### Substrate

A source of raw personal data — mailbox, calendar, browser history/bookmarks, screenshots, tabs, agent-memory store, web clippings, NAS exports, manual notes. Each substrate produces material that may flow into `<vault>/raw/` (see [docs/concept.md](docs/concept.md)). Some substrates are referenced (mailbox bodies stay in IMAP; only metadata reaches `raw/`); others are owned (web clippings + audio + papers + agent-memory snapshots have copies stored in `raw/`). The split is deliberate; see [docs/concept.md § Storage rules](docs/concept.md).

### Collector

The substrate-specific module that turns a substrate into `raw/` files. One Collector per substrate, not per backend. `EmailCollector` covers all mailbox backends; `BrowserCollector` covers Firefox + Chrome; etc. Implementation: `scripts/collectors/<name>.py`. Discovered at runtime via [Registry](#registry).

### Substrate-with-accounts

A substrate where one operator has multiple identities. Email and calendar are account-substrates: `CONFIG.personal.accounts.<id>` lists each. Browser, screenshots, tabs are not — they're singletons.

### Account.kind

The discriminator that maps an `accounts.<id>` entry to concrete [Reader](#reader) and [Filter](#filter) adapters. CONFIG schema:

```yaml
personal:
  accounts:
    work:
      email: x@example.com
      reader: { kind: thunderbird-mbox, mbox_paths: [...] }
      filter: { kind: all-inkl-procmail, ... }
    private:
      email: y@gmail.com
      reader: { kind: gmail-api, oauth_token_env: GMAIL_OAUTH }
      filter: { kind: gmail-api, ... }
```

`reader.kind` and `filter.kind` are independent — an account can read via one backend and write rules via another (the legacy "Thunderbird mbox + All-Inkl Procmail" hybrid is exactly this).

### Domain types

The Python types that flow through the engine — neither adapter-specific nor collector-specific. Live in `scripts/domain/mail.py` (and future `scripts/domain/<substrate>.py`):

- `MessageMeta` — frozen dataclass: id, account_id, folder, from_addr, to_addrs, subject, date, size_bytes, in_reply_to, message_id
- `Message` — `MessageMeta` + body_text, body_html, attachment_filenames
- `FilterRule` — name + `FilterCondition` + `FilterAction`
- `FilterCondition` — from_addrs, subject_contains, body_contains (all OR-combined)
- `FilterAction` — kind (move|tag|flag|delete) + target

Adapters import from `domain/`; the reverse import is forbidden.

## Architecture

This codebase uses the [improve-codebase-architecture skill's vocabulary](https://skills.gooseworks.ai). Key terms below; full reference in that skill's `LANGUAGE.md`.

### Module

Anything with an interface and an implementation. Functions, classes, packages, slices.

### Interface

Everything a caller must know to use a module: types, invariants, error modes, ordering, config — not just the type signature.

### Depth

Leverage at the interface. Deep = a lot of behavior behind a small interface. Shallow = interface nearly as complex as the implementation.

### Seam

Where an interface lives. A place behavior can be altered without editing in place. Use this term, not "boundary."

### Adapter

A concrete thing satisfying an interface at a seam. Each [Reader](#reader) implementation is an adapter. Each [Filter](#filter) implementation is an adapter.

### Reader

The read-side mailbox seam. Stateless `Protocol` (Python). Methods: `list_folders()`, `scan_metadata(folder, since)`, `scan_deep(folder, limit, since)`. Adapters: `ThunderbirdMboxReader`, `GmailReader`, `ImapReader`. Defined in `scripts/adapters/mailbox/base.py`. Account → Reader resolution lives in `scripts/adapters/mailbox/__init__.py:resolve_reader()`.

### Filter

The write-side mailbox seam. Stateless `Protocol`. Methods: `apply(rule, dry_run)`, `list_existing()`. Adapters: `ThunderbirdMsgFilter`, `GmailFilter`, `AllInklProcmailFilter`. Same module + resolution pattern as [Reader](#reader).

The Read and Filter seams are **independent** — a Reader and a Filter for the same account-id can be different kinds (legacy: read Thunderbird mbox, write All-Inkl Procmail).

### Registry

The auto-discovery layer for [Collectors](#collector). `scripts/collectors/base.py` exports a `@register` decorator; each `scripts/collectors/<name>.py` registers its Collector class on import. `scripts/collectors/__init__.py` imports all submodules to trigger registration. `flush.py:piggyback_collectors()` and the `wiki collect` CLI both consume `Registry.all_collectors()`.

### CollectorSpec

The static declaration on each Collector class — `name`, `output_subfolder`, `piggyback_default`, `piggyback_cooldown_hours`, `supports_incremental`, `supports_account_loop`. Drives Registry queries + piggyback discovery + CLI dispatch.

### Graceful agnostic

Design rule: a Collector / Adapter whose required CONFIG keys are empty MUST `is_configured() → False` and be silently skipped, NOT crash. Examples: `EmailCollector` with zero accounts whose Reader-kind resolves; `BrowserCollector` with neither `firefox_profile` nor Chrome paths set. Empty config → empty work, no error.

## Out of scope (for now)

- Multi-vault ingest (one engine writing to N vaults).
- Concurrent collector execution. Sequential is the contract; parallelism is implementation-side, not interface-side.
- Adapters for substrates without an `accounts.<id>` entry. Browser/calendar/etc. don't get the Reader+Filter pattern (they're singletons).
