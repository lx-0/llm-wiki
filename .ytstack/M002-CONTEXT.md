---
milestone: M002
project: llm-wiki
created: 2026-05-02T14:47:46Z
size: M
---

# M002 — Context

## Goal

Email scanning and filter-application work for Gmail accounts (in addition to the existing Thunderbird-mbox + All-Inkl-Procmail combination) via a Reader / Filter adapter seam, so a new mailbox backend can be added without touching `scan-email` or `execute-suggestions` call-sites.

## Why now

The existing `scripts/scan-email.py` is hardcoded to Thunderbird mbox files; `scripts/thunderbird-rules.py` mixes three unrelated filter implementations (Thunderbird msgFilterRules, All-Inkl webmail Procmail, Gmail filter API) in one ~800-line file; `scripts/execute-suggestions.py:163-185` branches on account type at the call site (`if has_procmail_support … elif is_gmail_account … else msgFilterRules`). Adding any new backend means duplicating the Thunderbird-shaped read path or extending the if/elif chain. Per the deletion test in the architecture review (2026-05-02): removing the proposed Reader/Filter seam concentrates complexity in three call sites instead of dispersing it across N+1 of them — the seam earns its keep with two adapters, and we already have evidence we'll want at least three (Thunderbird-mbox / Gmail-API / All-Inkl-Procmail).

## Architectural decisions locked during the design grill

All decisions below were grilled through the `improve-codebase-architecture` skill flow on 2026-05-02. They are the source of truth for slice planning; deviations need explicit reopening.

### Q1 — Reader and Filter are separate seams (Option B)

A `MailboxReader` Protocol and a `MailboxFilter` Protocol — independently resolvable per account. The legacy "Thunderbird mbox read + All-Inkl Procmail write" hybrid is exactly this case: one account uses two different backends across the read/write split. Forcing both into one Adapter would be a regression.

### Q2 — `kind` discriminator nested per side

CONFIG schema:

```yaml
personal:
  accounts:
    work:
      email: x@example.com
      reader: { kind: thunderbird-mbox, mbox_paths: [...] }
      filter: { kind: all-inkl-procmail, imap_host: ..., imap_user_env: ..., imap_pass_env: ... }
    private:
      email: y@gmail.com
      reader: { kind: gmail-api, oauth_token_env: GMAIL_OAUTH }
      filter: { kind: gmail-api, oauth_token_env: GMAIL_OAUTH }
```

`reader.kind` and `filter.kind` are independent. `email` and `label` stay top-level on the account.

### Q3 — Definition-side parallelism only

The CONFIG schema supports N accounts of mixed kinds. Execution stays sequential (the EmailCollector loops accounts serially). No async, no thread pool inside the Collector. If concurrency becomes load-bearing later, it sits behind the seam, not on the interface.

### T1 — Stateless Protocol (Option A)

Adapters are Python `Protocol` types, not ABCs. Adapters MAY cache connections internally; the contract doesn't require it. Construction: `ThunderbirdMboxReader(account_id, mbox_paths=[...])` — no Registry call needed for tests. Tests instantiate `FakeReader(messages=[...])` directly.

### T2 — Domain types live in `scripts/domain/mail.py` (Option B)

`MessageMeta`, `Message`, `FilterRule`, `FilterCondition`, `FilterAction` are frozen dataclasses owned by the domain layer. Adapters import from `domain/`. Collectors import from `domain/`. Reverse imports (domain importing from adapter) are forbidden.

### T3 — Registry via `@register` decorator (Option A)

`scripts/collectors/base.py` exports a `register` decorator. Each Collector subclass uses it. `scripts/collectors/__init__.py` imports all submodules to trigger registration. `Registry.all_collectors()` and `Registry.piggyback_collectors()` are the read APIs.

### T4 — `wiki collect <name>` is the only CLI; old `scan-*.py` deleted (Option A, no shims)

No backwards compatibility — the operator is also the maintainer. `scripts/scan-email.py` and `scripts/thunderbird-rules.py` go away during S02. `wiki collect <name>` becomes the operator-facing entry; `wiki collect --list` enumerates registered collectors.

### T5 — Old CONFIG schema = hard error with migration hint (Option C, no shim)

`wiki_config.py` raises a `ConfigError` if it sees the legacy top-level `mbox_paths` / `has_procmail` / `imap_host` fields outside a `reader:` / `filter:` block. The error message points at the new schema and lists the keys it found. Operator migrates `config.yaml` once, manually.

## Domain vocabulary

New terms introduced by this milestone (full glossary in [CONTEXT.md](../CONTEXT.md)):

- **Reader** — read-side mailbox adapter Protocol
- **Filter** — write-side mailbox adapter Protocol
- **Adapter** — a concrete Reader or Filter implementation (Thunderbird-mbox, Gmail-API, …)
- **Account.kind** — the discriminator that maps `accounts.<id>` to concrete adapters
- **Collector** — substrate-level module (one per substrate, not per backend); existing concept, formalized this milestone
- **Registry** — auto-discovery layer for Collectors
- **CollectorSpec** — static declaration on each Collector class

## Exit criteria

- [ ] `scripts/domain/mail.py` exists and exports `MessageMeta`, `Message`, `FilterRule`, `FilterCondition`, `FilterAction` as frozen dataclasses.
- [ ] `scripts/adapters/mailbox/{base,thunderbird,gmail,allinkl}.py` ship the Protocol + 3 concrete adapter pairs. `resolve_reader(account)` / `resolve_filter(account)` dispatch on `account.reader.kind` / `account.filter.kind` and return `None` for unknown kinds (graceful agnostic).
- [ ] `scripts/collectors/base.py` ships the `Collector` Protocol + `CollectorSpec` + `@register` decorator + `all_collectors()` / `piggyback_collectors()` / `is_configured`-aware filtering. `scripts/collectors/email.py` ships `EmailCollector` that iterates `CONFIG.personal.accounts`, dispatches Reader per account, writes to `raw/notes/email/`.
- [ ] `wiki collect <name>` and `wiki collect --list` work. `wiki collect email --dry-run` runs the EmailCollector with no side effects.
- [ ] `flush.py` replaces hardcoded `_PIGGYBACK_COMMANDS` with `piggyback_collectors()` discovery; piggyback list comes from each Collector's `SPEC.piggyback_default` + `SPEC.piggyback_cooldown_hours`.
- [ ] `scripts/scan-email.py` and `scripts/thunderbird-rules.py` are deleted. `scripts/execute-suggestions.py:163-185` no longer has `if has_procmail_support / elif is_gmail / else`; it calls `resolve_filter(account).apply(rule)` uniformly.
- [ ] `wiki_config.py:Personal.accounts` requires nested `reader:` / `filter:` blocks. Old top-level fields raise `ConfigError` with a migration hint.
- [ ] Smoke test (live, end-to-end): with a real Gmail account configured, `wiki collect email --account <id>` writes a `raw/notes/email/<account>-<date>.md` report. Filter-side: a YAML `FilterRule` in `raw/suggestions/` gets applied via Gmail API on operator-approval.

## Decisions locked in discuss phase

(Append decisions here as they're made during slicing + execution. Format: "YYYY-MM-DD: decided X because Y.")

## Open questions

- **Gmail OAuth flow.** Where does the OAuth token live, and how is it refreshed? Current `wiki_config.py` reads env-var names (`*_env` fields). Gmail-API will need an OAuth-token cache that survives across runs. Resolve during S03 plan-task.
- **`raw/notes/email/` filename convention with multiple accounts.** Single-file-per-day per-account vs single-file-per-day with multi-account section? Affects index/dedup. Resolve during S02.
- **Backwards-compat for existing `state.json` keys.** `scripts/state/email-state.json` has Thunderbird-shaped per-mbox-path keys. After migration, key shape changes (per-account, not per-mbox-path). Migration step needed inside S02 or one-time hand-edit by operator. Decide during S02 plan-task.
