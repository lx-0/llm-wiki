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

### Producer

A module that consumes a *compiled* knowledge source (a file under `<vault>/raw/` that has already been turned into a wiki article by `compile.py`) and emits **derived material** somewhere else — suggestion notes, knowledge-gap requests, third-party belief extractions. Mirrors [Collector](#collector) but operates on the **opposite side** of the engine:

| | Collector | Producer |
|---|---|---|
| Reads from | outside the vault (mailbox, browser, calendar, …) | inside the vault (a just-compiled source file) |
| Writes to | `<vault>/raw/<subfolder>/` | `<vault>/raw/requests/`, `<vault>/raw/suggestions/`, `<vault>/knowledge/takes/` |
| Trigger | `wiki collect` / piggyback after flush | per-source post-pass inside compile.py's loop |
| CLI verb | `wiki collect <name>` | `wiki produce <name> <source>` |

Today's Producers: `suggestions` (email-source action items via Claude SDK), `curiosity` (knowledge-gap requests via Ollama gemma4), `takes` (third-party belief extraction via Claude SDK, M011). Implementation: `scripts/producers/<name>.py`. Discovered at runtime via [ProducerRegistry](#producerregistry).

Disambiguation: DECISIONS.md occasionally uses lowercase "producer" loosely (e.g. "dashboard_stats.py is the producer of the dashboard cache"). The capitalized term is the concept defined here.

### ProducerSpec

The static declaration on each Producer class — `name`, `enabled_config_key`, `source_glob_config_key`. Drives ProducerRegistry queries + per-source gate checks + CLI dispatch. Parallel to [CollectorSpec](#collectorspec).

```python
@dataclass(frozen=True)
class ProducerSpec:
    name: str
    enabled_config_key: str | None       # e.g. "features.extract_takes"; None = always on
    source_glob_config_key: str | None   # e.g. "limits.extract_takes_source_globs"; None = every source
```

Both gates are evaluated by the **orchestrator** (compile.py's post-pass loop), not by the Producer. Producers do not duplicate gate-check code internally — they assume that if `run()` is called, the gates passed.

### ProducerResult

What `Producer.run()` returns. Replaces today's `None`-returning shape so per-source aggregation, cost reporting, and end-of-run summaries become possible.

```python
@dataclass(frozen=True)
class ProducerResult:
    producer: str                        # SPEC.name
    status: Literal["ok", "skipped", "failed"]
    reason: str | None                   # why skipped/failed (None when ok)
    cost_usd: float                      # 0.0 for local-only producers (curiosity)
    outputs: tuple[Path, ...]            # files written
```

Failure contract: a `failed` Producer **never blocks** the compile-source state save. The orchestrator wraps each `Producer.run()` in a try/except, logs the result, marks the Producer failed for this source, and proceeds. Quiet bug it prevents: a curiosity-pass crash today silently skips the per-file state save (state save is after all three `await`s), causing the next compile run to re-spend Claude SDK tokens recompiling the same source.

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

### ProducerRegistry

The auto-discovery layer for [Producers](#producer). Same shape as [Registry](#registry) but parallel — Producers live in `scripts/producers/`, register via their own `@register` decorator, and are consumed by `compile.py`'s post-pass loop + the `wiki produce` CLI. Kept separate (not merged into Registry) because Collectors and Producers have different lifecycles, different config trees, and different CLI verbs — conflating them creates the same misnomer trap as `flush.py:_LEGACY_PIGGYBACK_COMMANDS`.

Registration order **is** run order. Today's order is preserved across the refactor: suggestions → curiosity → takes (matches the historical `await` sequence in `compile.py:1272-1281`).

### CollectorSpec

The static declaration on each Collector class — `name`, `output_subfolder`, `piggyback_default`, `piggyback_cooldown_hours`, `supports_incremental`, `supports_account_loop`. Drives Registry queries + piggyback discovery + CLI dispatch.

### Graceful agnostic

Design rule: a Collector / Adapter whose required CONFIG keys are empty MUST `is_configured() → False` and be silently skipped, NOT crash. Examples: `EmailCollector` with zero accounts whose Reader-kind resolves; `BrowserCollector` with neither `firefox_profile` nor Chrome paths set. Empty config → empty work, no error.

## Out of scope (for now)

- Multi-vault ingest (one engine writing to N vaults).
- Concurrent collector execution. Sequential is the contract; parallelism is implementation-side, not interface-side.
- Adapters for substrates without an `accounts.<id>` entry. Browser/calendar/etc. don't get the Reader+Filter pattern (they're singletons).
