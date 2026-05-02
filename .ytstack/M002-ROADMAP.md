---
milestone: M002
project: llm-wiki
size: M
created: 2026-05-02T14:47:46Z
status: done-pending-live-smoke
total_slices: 3
completed_slices: 3
---

# M002 Roadmap

**Goal:** Email scanning and filter-application work for Gmail accounts via a Reader / Filter adapter seam, so a new mailbox backend can be added without touching `scan-email` or `execute-suggestions` call-sites.

**Exit criteria** (full list in `M002-CONTEXT.md`):

- [ ] `scripts/domain/mail.py` ships frozen-dataclass domain types
- [ ] Reader + Filter Protocols + 3 adapter pairs in `scripts/adapters/mailbox/`
- [ ] `Collector` Protocol + `CollectorSpec` + `Registry` in `scripts/collectors/base.py`; `EmailCollector` consumes the seam
- [ ] `wiki collect <name>` CLI subcommand replaces `scripts/scan-email.py` (deleted)
- [ ] `flush.py` discovers piggybacks via `Registry`, no hardcoded list
- [ ] `execute-suggestions.py` dispatches via `resolve_filter(account)`, no `if/elif/else` on account type
- [ ] `wiki_config.py` enforces new nested `reader:` / `filter:` schema; old schema raises `ConfigError`
- [ ] Smoke test: Gmail account configured → `wiki collect email --account <id>` runs end-to-end

## Slices

Slice detail lives in per-slice `M002-S##-PLAN.md` files, created by `ytstack:slice-milestone`. Tentative breakdown locked during architecture grill (subject to refinement during slicing):

- [x] **S01 — Backbone + first proof.** `domain/mail.py` types. `collectors/base.py` (Spec + Protocol + Registry + decorator). `adapters/mailbox/base.py` (Reader + Filter Protocols). `EmailCollector` skeleton with `FakeReader`-driven test (no real adapters yet). `wiki collect` CLI subcommand wired into `wiki` dispatcher. **Outcome:** architecture stands; `wiki collect --list` shows `email`; `wiki collect email --dry-run` runs against a fake reader and writes a sample `raw/notes/email/<fake>.md`. No real backend yet, but the seam is provable.

- [x] **S02 — Migrate existing capability.** `ThunderbirdMboxReader` + `ThunderbirdMsgFilter` + `AllInklProcmailFilter` adapters. `wiki_config.py:Personal.accounts` schema migrated to nested `reader:` / `filter:` blocks; old schema = hard `ConfigError`. `scripts/scan-email.py` + `scripts/thunderbird-rules.py` deleted; functionality preserved through adapters. `scripts/execute-suggestions.py:163-185` refactored to `resolve_filter(account).apply(rule)` — no `if/elif`. `flush.py:_PIGGYBACK_COMMANDS` replaced by `Registry.piggyback_collectors()` discovery. Operator migrates own `config.yaml` once. **Outcome:** every Thunderbird-mbox + All-Inkl-Procmail capability works exactly as before, only via the new seam.

- [x] **S03 — Add Gmail (the actual goal).** `GmailReader` + `GmailFilter` adapters via Gmail API. OAuth token cache strategy resolved (open question from CONTEXT). User can declare `accounts.private = { reader: { kind: gmail-api, … }, filter: { kind: gmail-api, … } }` and `wiki collect email --account private` runs end-to-end against the real Gmail API. **Outcome:** the original use-case "scan-email mit Gmail" is live; multi-account multi-kind setup works in production.

## Out of scope (deferred — open as M003+ candidates)

- Other substrates (calendar, browser, screenshots, tabs) migrated to the Collector pattern. Mailbox is the proving ground; once the seam shape is validated, M003 can roll the pattern out across the rest.
- IMAP-direct adapter (read or filter via Sieve). Worth adding once a non-Gmail non-AllInkl IMAP account shows up.
- Async / parallel collector execution. Definition-side parallelism only for M002.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done`
